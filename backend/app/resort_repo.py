"""Sort-again requests as the web role (U-label-structure-21, ADR-0056).

The api has no INSERT on the request table: a request is made through ``categories.request_resort`` alone, which checks
the threshold and refuses while a plan is open. Every query filters on the mailbox id.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta  # datetime is used as the type of a parameter at run time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.errors import RateLimited
from app.plan_repo import PlanConflict, refusal_of

if TYPE_CHECKING:
    import uuid

    from app.db import Database

_WINDOW = timedelta(hours=1)
_HOUR = int(_WINDOW.total_seconds())

# One request at a time per mailbox: the checks below and the insert in the function see the same state.
_LOCK = text("SELECT pg_advisory_xact_lock(hashtext(:key))")
_RECENT = text(
    "SELECT count(*) AS requests, min(at) AS oldest FROM categories.resort_request "
    "WHERE mailbox_id = :mailbox AND at > :since"
)
# A request still waits for the agent when it is the latest one and no plan carries its id yet.
_UNANSWERED = text(
    "SELECT 1 FROM (SELECT id FROM categories.resort_request WHERE mailbox_id = :mailbox "
    "ORDER BY at DESC, id DESC LIMIT 1) r "
    "WHERE NOT EXISTS (SELECT 1 FROM categories.plan p WHERE p.mailbox_id = :mailbox AND p.request_id = r.id)"
)
_REQUEST = text("SELECT categories.request_resort(:mailbox, :threshold)")
_LATEST = text(
    "SELECT threshold FROM categories.resort_request WHERE mailbox_id = :mailbox ORDER BY at DESC, id DESC LIMIT 1"
)


class ResortRepository:
    """Makes and reads the sort-again requests of one mailbox."""

    def __init__(self, database: Database, mailbox_id: str) -> None:
        """Keep the database access and the mailbox every query is limited to."""
        self._database = database
        self._mailbox = mailbox_id

    async def latest_threshold(self) -> int | None:
        """Return the threshold of the newest request, or None when there is none."""
        async with self._database.session() as session, session.begin():
            value = (await session.execute(_LATEST, {"mailbox": self._mailbox})).scalar_one_or_none()
        return None if value is None else int(value)

    async def request(self, threshold: int, now: datetime, per_hour: int) -> uuid.UUID:
        """Make a request when the hourly limit, an unanswered request and an open plan allow it.

        Args:
            threshold: The whole number from 50 to 100 (the database checks it again).
            now: The time of the request, from the application's clock.
            per_hour: The most requests of the last hour.

        Returns:
            The id of the new request.

        Raises:
            RateLimited: The hourly limit is used up; carries the wait until the oldest request is an hour old.
            PlanConflict: A plan is open, or the latest request has not become a plan yet; nothing was written.
            PlanMalformed: The database refused the threshold.
            DBAPIError: Any other database failure (not translated).
        """
        params = {"mailbox": self._mailbox}
        try:
            async with self._database.session() as session, session.begin():
                await session.execute(_LOCK, {"key": f"resort-request:{self._mailbox}"})
                recent = (await session.execute(_RECENT, {**params, "since": now - _WINDOW})).one()
                if recent.requests >= per_hour:
                    wait = math.ceil((recent.oldest + _WINDOW - now).total_seconds())
                    raise RateLimited(max(1, min(_HOUR, wait)))
                if (await session.execute(_UNANSWERED, params)).first() is not None:
                    raise PlanConflict
                created = await session.execute(_REQUEST, {**params, "threshold": Decimal(threshold)})
                return created.scalar_one()
        except DBAPIError as error:
            refusal = refusal_of(error)
            if refusal is None:
                raise
            raise refusal from None  # not chained: the driver text is not for the response
