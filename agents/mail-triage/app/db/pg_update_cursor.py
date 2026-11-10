"""The id of the last handled Telegram update, kept in ``poll_state`` so it survives a restart (RT-5).

Telegram redelivers the update that was never acknowledged. Typed text is bound to whatever question is pending, so a
redelivered answer would be read as the answer to the next question. The id only moves forward.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.db.models import PollState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

POLL_ROW = 1


class PgUpdateCursor:
    """Reads and advances the stored id; every call is one short transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def last(self) -> int | None:
        """The id of the last handled update, or ``None`` when none was handled yet."""
        async with self._sessions() as session:
            row = await session.get(PollState, POLL_ROW)
        return row.telegram_update_id if row else None

    async def advance(self, update_id: int) -> None:
        """Store ``update_id`` unless a higher id is stored already."""
        statement = insert(PollState).values(id=POLL_ROW, telegram_update_id=update_id)
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "telegram_update_id": func.greatest(PollState.telegram_update_id, statement.excluded.telegram_update_id)
            },
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)
