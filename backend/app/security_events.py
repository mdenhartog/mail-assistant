"""Security event store: one row per kind, client and minute in `web_auth.security_event` (U-web-settings-13).

The web role may only select and insert there. Repeats of the same kind from one client in one window hit the unique
constraint and are dropped (``ON CONFLICT DO NOTHING``), so a flood cannot grow the table. The row holds no free text:
the username only as its keyed digest, never an address or an error message. A failing insert never reaches the
caller, which is busy refusing a request; only the error class is logged.
"""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth.event_rules import client_class, event_window, result_for, valid_username_hash
from app.clock import Clock
from app.db import Database, DatabaseUnavailable

logger = logging.getLogger(__name__)

_INSERT = text(
    'INSERT INTO web_auth.security_event (kind, result, username_hash, request_id, client_key, "window") '
    "VALUES (:kind, :result, :username_hash, :request_id, :client_key, :window) "
    "ON CONFLICT ON CONSTRAINT uq_security_event_kind_client_window DO NOTHING"
)


class SecurityEvents:
    """Writes `web_auth.security_event` as the web role."""

    def __init__(self, database: Database, clock: Clock) -> None:
        """Keep the database access and the clock."""
        self._database = database
        self._clock = clock

    async def record(self, kind: str, request_id: str, client: str, username_hash: str | None = None) -> None:
        """Record one event and log one line about it.

        Args:
            kind: One of the kinds of the table.
            request_id: The request id of the refused or logged request.
            client: The client key (U-24); only its family is logged.
            username_hash: The keyed digest of a username (U-10), never the username.

        Raises:
            ValueError: The kind is unknown or the username hash is not a digest; nothing is written.
        """
        result = result_for(kind)
        if username_hash is not None and not valid_username_hash(username_hash):
            raise ValueError("username hash is not a digest")
        logger.info(
            "security_event kind=%s result=%s client=%s request_id=%s", kind, result, client_class(client), request_id
        )
        parameters = {
            "kind": kind,
            "result": result,
            "username_hash": username_hash,
            "request_id": request_id,
            "client_key": client,
            "window": event_window(self._clock.now()),
        }
        try:
            async with self._database.session() as session, session.begin():
                await session.execute(_INSERT, parameters)
        except (DatabaseUnavailable, SQLAlchemyError) as error:
            logger.error("security_event.failed kind=%s error_class=%s", kind, type(error).__name__)
