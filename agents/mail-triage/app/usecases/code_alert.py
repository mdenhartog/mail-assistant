"""Stub of the wrong-code alert (U-web-settings-48); the real body follows the failing tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime


class EventSource(Protocol):
    """Security events."""

    async def refused_codes(self, since: datetime) -> int:
        """Sum of ``count`` of ``code_refused`` events newer than ``since``."""
        ...


class Say(Protocol):
    """A plain note to Marco."""

    async def say(self, text: str) -> None:
        """Send it."""
        ...


class CodeAlert:
    """Stub."""

    def __init__(self, events: EventSource, chat: Say) -> None:
        """Keep the parts."""
        self._events = events
        self._chat = chat

    async def run(self, now: datetime) -> None:
        """Stub."""
        raise NotImplementedError
