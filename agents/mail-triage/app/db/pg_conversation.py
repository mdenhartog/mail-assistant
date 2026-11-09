"""The one pending Telegram dialogue, stored in the single ``conversation`` row (ADR-0026, spec C-8).

Starting a dialogue replaces the current one. Every start and every advance issues a new random nonce, so a button or
answer made for an earlier step no longer matches. A dialogue without a time limit (snooze and reply questions) stores
``NO_EXPIRY``, a moment far in the future, because the column is not nullable; callers never see that value.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Conversation

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROW = 1
NO_EXPIRY: Final = datetime(9999, 12, 31, tzinfo=UTC)
NONCE_BYTES = 16

Kind = Literal["snooze", "reply", "settings"]


@dataclass(frozen=True, slots=True)
class OpenConversation:
    """The pending dialogue. ``expires_at`` is ``None`` when it has no time limit."""

    kind: str
    target: str | None
    step: str
    partial: dict[str, object]
    nonce: str
    expires_at: datetime | None


def _open(row: Conversation) -> OpenConversation:
    return OpenConversation(
        kind=row.kind,
        target=row.target,
        step=row.step,
        partial=dict(row.partial),
        nonce=row.nonce,
        expires_at=None if row.expires_at == NO_EXPIRY else row.expires_at,
    )


def _nonce() -> str:
    return secrets.token_urlsafe(NONCE_BYTES)


class ConversationStore:
    """Start, read, advance and clear the single pending dialogue."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], now: Callable[[], datetime]) -> None:
        """Keep the session factory and the clock (expiry is judged by this clock)."""
        self._sessions = sessions
        self._now = now

    async def start(
        self, kind: Kind, target: str | None, step: str, partial: dict[str, object], ttl: timedelta | None
    ) -> OpenConversation:
        """Replace whatever is pending with a new dialogue; ``ttl=None`` means it never expires."""
        values = {
            "kind": kind,
            "target": target,
            "step": step,
            "partial": partial,
            "nonce": _nonce(),
            "expires_at": NO_EXPIRY if ttl is None else self._now() + ttl,
        }
        statement = insert(Conversation).values(id=ROW, **values)
        statement = statement.on_conflict_do_update(index_elements=[Conversation.id], set_=values)
        async with self._sessions.begin() as session:
            row = (await session.execute(statement.returning(Conversation))).scalar_one()
            return _open(row)

    async def current(self) -> OpenConversation | None:
        """The pending dialogue, or ``None`` when there is none or it has expired (expiry is exclusive)."""
        statement = select(Conversation).where(Conversation.id == ROW, Conversation.expires_at > self._now())
        async with self._sessions() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        return _open(row) if row else None

    async def advance(self, nonce: str, step: str, partial: dict[str, object]) -> OpenConversation | None:
        """Move the dialogue to the next step if ``nonce`` is the current one and it is alive; rotates the nonce."""
        statement = (
            update(Conversation)
            .where(Conversation.id == ROW, Conversation.nonce == nonce, Conversation.expires_at > self._now())
            .values(step=step, partial=partial, nonce=_nonce())
            .returning(Conversation)
        )
        async with self._sessions.begin() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
            return _open(row) if row else None

    async def clear(self) -> None:
        """Forget the pending dialogue."""
        async with self._sessions.begin() as session:
            await session.execute(delete(Conversation).where(Conversation.id == ROW))
