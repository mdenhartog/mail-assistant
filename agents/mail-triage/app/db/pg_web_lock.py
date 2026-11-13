"""The web sign-in lock in PostgreSQL (ADR-0033): the one row of ``web_auth.web_lock``.

The agent role may select, insert, update and delete on this one table and on nothing else in ``web_auth``
(``app/db/grants.sql``). The table holds at most one row (a check on ``id``), so setting the lock twice is one row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import WebLock

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROW: Final = 1


class PgWebLock:
    """Satisfies ``LockStore``; every call is one short transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def lock(self, now: datetime) -> bool:
        """Set the lock; ``True`` when this call set it. When it was already set nothing changes (the time stays)."""
        statement = (
            insert(WebLock)
            .values(id=ROW, locked_at=now)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(WebLock.id)
        )
        async with self._sessions.begin() as session:
            created = await session.execute(statement)
        return created.first() is not None

    async def is_locked(self) -> bool:
        """``True`` while the lock row exists."""
        async with self._sessions() as session:
            return (await session.execute(select(WebLock.id).where(WebLock.id == ROW))).first() is not None

    async def unlock(self) -> bool:
        """Delete the lock row; ``True`` when there was one."""
        async with self._sessions.begin() as session:
            deleted = await session.execute(delete(WebLock).where(WebLock.id == ROW).returning(WebLock.id))
        return deleted.first() is not None
