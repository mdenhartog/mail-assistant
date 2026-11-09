"""The overview log: which local dates were settled and the instant each was settled (AC-27, ADR-0027).

The log is keyed by the local date in the zone in force when the overview was settled; the instant is what starts the
window of the next overview, so a change of zone can neither skip nor repeat a mail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import OverviewLog

if TYPE_CHECKING:
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class PgOverviewLog:
    """Satisfies ``OverviewLog`` of the overview use case."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def overview_sent(self, day: date) -> bool:
        """Whether the overview of this local date was settled."""
        async with self._sessions() as session:
            return await session.get(OverviewLog, day) is not None

    async def mark_overview_sent(self, day: date, settled_at: datetime) -> None:
        """Remember that the overview of this local date was settled at ``settled_at``; the first instant stays."""
        statement = insert(OverviewLog).values(day=day, settled_at=settled_at).on_conflict_do_nothing()
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def last_settled_at(self) -> datetime | None:
        """The latest settled instant, or None when no overview was ever settled."""
        async with self._sessions() as session:
            return (await session.execute(select(func.max(OverviewLog.settled_at)))).scalar_one()
