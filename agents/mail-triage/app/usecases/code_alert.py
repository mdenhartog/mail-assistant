"""Warn Marco in Telegram about repeated wrong sign-in codes on the web (spec AC-20, W-13; ADR-0039).

At each run the agent adds up the ``count`` of the ``code_refused`` security events newer than 10 minutes (one row holds
every wrong code of one client in one minute, so the rows are not counted, their counts are: SEC-04). At 5 or more it
sends one notice with that number and the time, and sends no second one before 10 minutes have passed. Every other kind
of event never counts. The notice holds a number and a time only: no code, username, address or digest, and nothing is
logged here (W-13, W-15). A failed send leaves no trace of a notice, so the next run tries again.

An event counts when it is newer than the window (``at > now - window``): one that is exactly 10 minutes old is out.
The time of a row is the time of its first event of the minute. The notice time is kept in memory: after a restart one
notice may come again, which is the cheap way to be wrong.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Final, Protocol

from app.core import settings_text

if TYPE_CHECKING:
    from datetime import datetime

WINDOW: Final = timedelta(minutes=10)
THRESHOLD: Final = 5


class EventSource(Protocol):
    """The security events (``PgSecurityEvents``)."""

    async def refused_codes(self, since: datetime) -> int:
        """Sum of ``count`` of the ``code_refused`` events newer than ``since``; no other kind is included."""
        ...


class Say(Protocol):
    """A plain note to Marco."""

    async def say(self, text: str) -> None:
        """Send it."""
        ...


class CodeAlert:
    """Sends the wrong-code notice."""

    def __init__(self, events: EventSource, chat: Say) -> None:
        """Wire the events and Telegram."""
        self._events = events
        self._chat = chat
        self._noticed_at: datetime | None = None

    async def run(self, now: datetime) -> None:
        """Send one notice when 5 or more wrong codes came in the last 10 minutes and none was sent in that time."""
        if self._noticed_at is not None and now - self._noticed_at < WINDOW:
            return
        count = await self._events.refused_codes(now - WINDOW)
        if count < THRESHOLD:
            return
        await self._chat.say(settings_text.code_alert(count, now))
        self._noticed_at = now
