"""Test doubles for the dialogue registry: an in-memory conversation row driven by a FakeClock, and a fake handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar

from app.db.pg_conversation import OpenConversation

if TYPE_CHECKING:
    from app.db.pg_conversation import Kind
    from schedule_policy.testing import FakeClock

NONCE_LENGTH = 22  # a 16-byte URL-safe token, like the real store's


class FakeConversations:
    """The single conversation row in memory; same rules as ``ConversationStore`` (expiry is exclusive)."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self._row: OpenConversation | None = None
        self._count = 0
        self.starts = 0

    def _nonce(self) -> str:
        self._count += 1
        return f"n{self._count:0{NONCE_LENGTH - 1}d}"

    async def start(
        self, kind: Kind, target: str | None, step: str, partial: dict[str, object], ttl: timedelta | None
    ) -> OpenConversation:
        self.starts += 1
        expires = None if ttl is None else self._clock.now() + ttl
        self._row = OpenConversation(kind, target, step, dict(partial), self._nonce(), expires)
        return self._row

    async def current(self) -> OpenConversation | None:
        row = self._row
        if row is None or (row.expires_at is not None and row.expires_at <= self._clock.now()):
            return None
        return row

    async def advance(self, nonce: str, step: str, partial: dict[str, object]) -> OpenConversation | None:
        row = await self.current()
        if row is None or row.nonce != nonce:
            return None
        self._row = OpenConversation(row.kind, row.target, step, dict(partial), self._nonce(), row.expires_at)
        return self._row

    async def clear(self) -> None:
        self._row = None


@dataclass
class FakeSettings:
    """A registered settings handler that records what the router hands it (the real dialogue is a later unit)."""

    kind: ClassVar[Kind] = "settings"
    commands: ClassVar[frozenset[str]] = frozenset({"/settings"})
    first_step: ClassVar[str] = "card"
    ttl: ClassVar[timedelta | None] = timedelta(minutes=15)
    began: list[OpenConversation] = field(default_factory=list)
    texts: list[tuple[str, str]] = field(default_factory=list)
    buttons: list[tuple[str, str, str]] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)

    async def begin(self, conversation: OpenConversation) -> None:
        self.began.append(conversation)

    async def on_text(self, conversation: OpenConversation, text: str) -> None:
        self.texts.append((conversation.nonce, text))
        self.writes.append(f"text:{text}")

    async def on_button(self, conversation: OpenConversation, action: str, argument: str) -> None:
        self.buttons.append((conversation.nonce, action, argument))
        self.writes.append(f"button:{action}:{argument}")
