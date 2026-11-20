"""A Telegram outbox double: records what would be sent and fails the test when a canary string leaks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.fakes.seeds import CANARIES

if TYPE_CHECKING:
    from app.core.alert_text import AlertMessage


class CanaryLeakError(AssertionError):
    """A notice carried a canary string, so mail content reached Telegram."""


class FakeTelegram:
    """Same send surface as ``TelegramOutbox``; texts are kept only when they are clean."""

    def __init__(self, canaries: tuple[str, ...] = CANARIES) -> None:
        self._canaries = tuple(c.casefold() for c in canaries)
        self.texts: list[str] = []
        self.callbacks: list[str] = []
        self._next_id = 0

    def _record(self, text: str) -> None:
        lowered = text.casefold()
        if any(canary in lowered for canary in self._canaries):
            raise CanaryLeakError("a canary string reached Telegram")  # never echo the text
        self.texts.append(text)

    async def send(self, message: AlertMessage) -> int:
        """Record an alert and return a fake message id."""
        self._record(message.text)
        self._next_id += 1
        return self._next_id

    async def say(self, text: str) -> None:
        """Record a plain note."""
        self._record(text)

    async def edit_message(self, message_id: int, text: str) -> None:
        """Record the replacement text."""
        self._record(text)

    async def offer(self, text: str, label: str, data: str) -> None:
        """Record a note with one button."""
        self._record(text)

    async def answer_callback(self, callback_id: str) -> None:
        """Record a pressed-button acknowledgement."""
        self.callbacks.append(callback_id)
