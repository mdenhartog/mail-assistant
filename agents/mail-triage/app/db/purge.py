"""The retention purge (AC-21, W-13, ADR-0030): old audit records and expired web rows are deleted by the owner role.

It is the last step of the migrate job (``python -m app migrate``) and can be run alone as ``python -m app purge``. It
needs the owner role on purpose: ``settings.settings_change`` is append-only for the runtime roles, and this owner
purge is the one documented delete path. It is not a standing job and not a runtime role.

Boundary rule, stated once: an audit record or a security event goes when its timestamp is **strictly older** than the
cutoff (``at < now - retention``). A record that is exactly as old as the retention stays and goes one run later.
Login requests and sessions follow the rules the web app applies itself at start-up (``backend/app/startup.py``): the
cutoff comparison is ``<=`` there, because an expiry moment that has been reached means expired.

The clock is injected. Only the number of removed rows is logged, never a row, a key or a hash.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

SETTINGS_CHANGE_RETENTION: Final = timedelta(days=365)  # Marco, 2026-11-13 (D-19)
SECURITY_EVENT_RETENTION: Final = timedelta(days=90)  # Marco, 2026-11-13 (D-19)
# Mirrors of the web app's values (backend/app/auth/login_requests.py and expiry.py); this component cannot import them.
LOGIN_REQUEST_RETENTION: Final = timedelta(hours=1)  # a dead request still counts for the hourly code cap
SESSION_IDLE: Final = timedelta(minutes=30)

_DELETE_SETTINGS_CHANGE = "DELETE FROM settings.settings_change WHERE at < $1"
_DELETE_SECURITY_EVENT = "DELETE FROM web_auth.security_event WHERE at < $1"
_DELETE_LOGIN_REQUEST = "DELETE FROM web_auth.login_request WHERE expires_at <= $1 AND created_at <= $2"
_DELETE_SESSION = "DELETE FROM web_auth.session WHERE absolute_expires_at <= $1 OR last_seen_at <= $2"


class Clock(Protocol):
    """Anything with a timezone-aware ``now``."""

    def now(self) -> datetime:
        """The current moment."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> datetime:
        """The current UTC moment."""
        return datetime.now(UTC)


SYSTEM_CLOCK: Final = SystemClock()


@dataclass(frozen=True)
class PurgeCounts:
    """How many rows each table lost."""

    settings_change: int
    security_event: int
    login_request: int
    session: int


def _removed(status: str) -> int:
    """The row count of an asyncpg command tag such as ``DELETE 3``."""
    return int(status.rsplit(" ", 1)[-1])


async def purge_expired(connection: asyncpg.Connection, clock: Clock) -> PurgeCounts:
    """Delete what is past its retention, in one transaction, and log the counts. Safe to run again."""
    now = clock.now()
    async with connection.transaction():
        counts = PurgeCounts(
            settings_change=_removed(
                await connection.execute(_DELETE_SETTINGS_CHANGE, now - SETTINGS_CHANGE_RETENTION)
            ),
            security_event=_removed(await connection.execute(_DELETE_SECURITY_EVENT, now - SECURITY_EVENT_RETENTION)),
            login_request=_removed(await connection.execute(_DELETE_LOGIN_REQUEST, now, now - LOGIN_REQUEST_RETENTION)),
            session=_removed(await connection.execute(_DELETE_SESSION, now, now - SESSION_IDLE)),
        )
    logger.info(
        "purge removed settings_change=%d security_event=%d login_request=%d session=%d",
        counts.settings_change,
        counts.security_event,
        counts.login_request,
        counts.session,
    )
    return counts
