"""The buttons of a web notice and the unlock command (spec C-8, AC-13, AC-27; ADR-0033)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from app.adapters.telegram_inbox import Command
    from app.db.repos import StoredSettings
    from app.usecases.web_notice import NoticeToken
    from schedule_policy.policy import TimePolicy


class TokenStore(Protocol):
    """The token records of the notices."""

    async def find(self, token: str) -> NoticeToken | None:
        """The record of ``token``, expired or not; ``None`` when there is none (never made, or used)."""
        ...

    async def burst_end(self, before: dict[str, object]) -> int:
        """The highest announced version among the tokens that restore the same ``before``."""
        ...

    async def consume(self, token: str) -> bool:
        """Delete the record of ``token``; ``True`` when this call deleted it."""
        ...


class LockStore(Protocol):
    """``web_auth.web_lock``."""

    async def lock(self, now: datetime) -> None:
        """Set the lock; setting it again changes nothing."""
        ...

    async def unlock(self) -> bool:
        """Delete the lock row; ``True`` when there was one."""
        ...


class SettingsWriter(Protocol):
    """The settings store, as far as an Undo needs it."""

    async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
        """Replace the row if it is still at ``expected_version``."""
        ...


class ChatPort(Protocol):
    """Telegram."""

    async def say(self, text: str) -> None:
        """A short plain note."""
        ...

    async def edit_message(self, message_id: int, text: str) -> None:
        """Replace a message's text and remove its buttons."""
        ...


class WebNoticeActions:
    """Handles ``webundo``, ``weblock`` and ``/web_unlock``."""

    def __init__(  # noqa: PLR0913 - every dependency is injected for tests
        self,
        tokens: TokenStore,
        lock: LockStore,
        settings: SettingsWriter,
        chat: ChatPort,
        *,
        chat_id: int,
        by: str,
        now: Callable[[], datetime],
    ) -> None:
        """Wire the stores, Telegram, the one allowed chat, the actor text of an Undo and the clock."""
        raise NotImplementedError

    async def on_button(self, command: Command, action: str, token: str) -> None:
        """Run ``webundo`` or ``weblock`` for ``token``."""
        raise NotImplementedError

    async def unlock(self, command: Command) -> None:
        """Lift the lock of web sign-in."""
        raise NotImplementedError
