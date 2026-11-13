"""Retention purge (stub for the red commit)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import asyncpg

    from app.db.engine import DatabaseTls


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


@dataclass(frozen=True)
class PurgeCounts:
    """How many rows each table lost."""

    settings_change: int
    security_event: int
    login_request: int
    session: int


async def purge_expired(connection: asyncpg.Connection, clock: Clock) -> PurgeCounts:
    """Stub."""
    raise NotImplementedError


async def purge_database(owner_url: str, tls: DatabaseTls | None, clock: Clock) -> PurgeCounts:
    """Stub."""
    raise NotImplementedError
