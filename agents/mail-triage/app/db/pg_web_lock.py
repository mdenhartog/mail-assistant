"""The web sign-in lock in PostgreSQL (ADR-0033): the one row of ``web_auth.web_lock``."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class PgWebLock:
    """Satisfies ``LockStore``; every call is one short transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def lock(self, now: datetime) -> None:
        """Set the lock."""
        raise NotImplementedError

    async def unlock(self) -> bool:
        """Delete the lock row."""
        raise NotImplementedError
