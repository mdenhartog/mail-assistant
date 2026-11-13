"""Security event store: one row per kind, client and minute in `web_auth.security_event` (U-web-settings-13, -54).

The web role may select and insert there, and update the column ``count`` only. A repeat of the same kind from one
client in one window hits the unique constraint. For a counted kind (wrong codes) it raises ``count`` (``ON CONFLICT DO
UPDATE``), so the alert can add the wrong codes up. For any other kind it is dropped (``DO NOTHING``), so a flood
writes one row a window. The row holds no free text: the username and the client only as keyed digests, never an
address or an error message. A failing insert never reaches the caller, which is busy refusing a request; only the
error class is logged.
"""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth.event_rules import client_class, counts_repeats, event_window, result_for, valid_username_hash
from app.auth.request_code_rules import client_hash
from app.clock import Clock
from app.db import Database, DatabaseUnavailable

logger = logging.getLogger(__name__)

_DROP_REPEAT = text(
    'INSERT INTO web_auth.security_event (kind, result, username_hash, request_id, client_key, "window") '
    "VALUES (:kind, :result, :username_hash, :request_id, :client_key, :window) "
    "ON CONFLICT ON CONSTRAINT uq_security_event_kind_client_window DO NOTHING"
)
_COUNT_REPEAT = text(
    'INSERT INTO web_auth.security_event (kind, result, username_hash, request_id, client_key, "window") '
    "VALUES (:kind, :result, :username_hash, :request_id, :client_key, :window) "
    "ON CONFLICT ON CONSTRAINT uq_security_event_kind_client_window "
    "DO UPDATE SET count = web_auth.security_event.count + 1"
)


class SecurityEvents:
    """Writes `web_auth.security_event` as the web role."""

    def __init__(self, database: Database, clock: Clock, hash_key: bytes) -> None:
        """Keep the database access, the clock and the key of the client digest."""
        self._database = database
        self._clock = clock
        self._hash_key = hash_key

    async def record(self, kind: str, request_id: str, client: str, username_hash: str | None = None) -> None:
        """Record one event and log one line about it.

        Args:
            kind: One of the kinds of the table.
            request_id: The request id of the refused or logged request.
            client: The client key (U-24); only its family is logged and only its keyed digest is stored.
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
            "client_key": client_hash(self._hash_key, client),
            "window": event_window(self._clock.now()),
        }
        try:
            async with self._database.session() as session, session.begin():
                await session.execute(_COUNT_REPEAT if counts_repeats(kind) else _DROP_REPEAT, parameters)
        except (DatabaseUnavailable, SQLAlchemyError) as error:
            logger.error("security_event.failed kind=%s error_class=%s", kind, type(error).__name__)
