"""The label rename plan as the web role (U-label-prefix-removal-11, ADR-0061).

The api reads the state, the plan items and the deleted labels and writes only through ``confirm_label_rename`` and
``request_label_restore``. Every query filters on the mailbox id. Label names are handed to the response, nowhere else.
"""

from __future__ import annotations

import uuid  # noqa: TC003  # the type of the ids the functions return
from dataclasses import dataclass
from datetime import datetime, timedelta  # datetime is used as the type of a parameter at run time
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.plan_repo import PlanMalformed, refusal_of

if TYPE_CHECKING:
    from app.db import Database

DEFAULT_RETENTION_DAYS = 30  # while the schedule has no row (the agent's purge uses the same)

_STATE = text("SELECT state, plan_hash FROM categories.label_migration WHERE mailbox_id = :mailbox")
_ITEMS = text(
    "SELECT label_id, old_name, new_name, mail_count, action, state FROM categories.label_rename_item "
    "WHERE mailbox_id = :mailbox ORDER BY mail_count DESC, old_name, label_id"
)
_KNOWN = text("SELECT label_id FROM categories.label_rename_item WHERE mailbox_id = :mailbox AND label_id = ANY(:ids)")
_CONFIRM = text("SELECT categories.confirm_label_rename(:mailbox, :hash, :skipped)")
_RESTORE = text("SELECT categories.request_label_restore(:mailbox)")
_RETENTION = text("SELECT coalesce((SELECT label_retention_days FROM settings.schedule WHERE id = 1), :default)")
_DELETED = text(
    "SELECT name, deleted_at FROM categories.deleted_label "
    "WHERE mailbox_id = :mailbox AND deleted_at >= :since ORDER BY deleted_at DESC, label_id_hash"
)


@dataclass(frozen=True)
class PlanItem:
    """One row of the plan."""

    label_id: str
    old_name: str
    new_name: str
    mail_count: int
    action: str
    state: str


@dataclass(frozen=True)
class Plan:
    """The migration state with its stored hash and the items."""

    state: str
    plan_hash: str | None
    items: list[PlanItem]


@dataclass(frozen=True)
class Deleted:
    """A deleted label."""

    name: str
    deleted_at: datetime


class LabelRenameRepository:
    """Reads and confirms the rename plan of one mailbox."""

    def __init__(self, database: Database, mailbox_id: str) -> None:
        """Keep the database access and the mailbox every query is limited to."""
        self._database = database
        self._mailbox = mailbox_id

    async def plan(self) -> Plan:
        """Return the state, the hash and the items (largest first); state ``none`` without a migration row."""
        params = {"mailbox": self._mailbox}
        async with self._database.session() as session, session.begin():
            head = (await session.execute(_STATE, params)).one_or_none()
            rows = (await session.execute(_ITEMS, params)).all()
        items = [PlanItem(r.label_id, r.old_name, r.new_name, r.mail_count, r.action, r.state) for r in rows]
        if head is None:
            return Plan("none", None, items)
        return Plan(head.state, head.plan_hash, items)

    async def confirm(self, plan_hash: str, skipped: list[str]) -> uuid.UUID:
        """Confirm the plan through the database function (idempotent for the same hash and skip set).

        Args:
            plan_hash: The hash the user saw.
            skipped: The label ids to leave alone.

        Returns:
            The id of the confirmation.

        Raises:
            PlanConflict: The hash is wrong, stale or replayed, or the state is not pending.
            PlanMalformed: A skipped id is not in the plan.
            DBAPIError: Any other database failure (not translated).
        """
        params = {"mailbox": self._mailbox}
        unique = sorted(set(skipped))
        try:
            async with self._database.session() as session, session.begin():
                if unique:
                    found = (await session.execute(_KNOWN, {**params, "ids": unique})).all()
                    if {r.label_id for r in found} != set(unique):
                        raise PlanMalformed
                done = await session.execute(_CONFIRM, {**params, "hash": plan_hash, "skipped": unique})
                return done.scalar_one()
        except DBAPIError as error:
            refusal = refusal_of(error)
            if refusal is None:
                raise
            raise refusal from None  # not chained: the driver text is not for the response

    async def restore(self) -> uuid.UUID:
        """Ask for the restore through the database function (one open request per mailbox).

        Returns:
            The id of the open request.

        Raises:
            PlanConflict: No label was renamed yet.
            DBAPIError: Any other database failure (not translated).
        """
        try:
            async with self._database.session() as session, session.begin():
                return (await session.execute(_RESTORE, {"mailbox": self._mailbox})).scalar_one()
        except DBAPIError as error:
            refusal = refusal_of(error)
            if refusal is None:
                raise
            raise refusal from None

    async def deleted(self, now: datetime) -> tuple[int, list[Deleted]]:
        """Return the retention in days and the labels deleted within it, newest first."""
        async with self._database.session() as session, session.begin():
            days = int((await session.execute(_RETENTION, {"default": DEFAULT_RETENTION_DAYS})).scalar_one())
            since = now - timedelta(days=days)
            rows = (await session.execute(_DELETED, {"mailbox": self._mailbox, "since": since})).all()
        return days, [Deleted(r.name, r.deleted_at) for r in rows]
