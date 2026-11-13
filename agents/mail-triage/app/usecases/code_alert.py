"""Warn about repeated wrong sign-in codes and lock web sign-in after too many (AC-20, AC-27, W-13; ADR-0039).

At each run the agent adds up the ``count`` of the ``code_refused`` security events (one row holds every wrong code of
one client in one minute, so the rows are not counted, their counts are: SEC-04). Every other kind never counts.

- 5 or more in the last 10 minutes: one notice with the number and the time, and no second one before 10 minutes have
  passed (U-web-settings-48).
- 15 or more in the last 24 hours: the agent sets the web lock once and sends one notice with the number, the time and
  ``/web_unlock``; that notice replaces the 10-minute one of the same run (U-web-settings-55). While the lock is set the
  agent writes nothing and sends nothing more. A notice that could not be sent is tried again on the next run.

An event counts when it is newer than the window (``at > now - window``): one that is exactly 10 minutes, or 24 hours,
old is out. The time of a row is the time of its first event of the minute.

The rule that keeps old events from locking again after ``/web_unlock``: events are *spent*. Every event with an id at
or below the newest id seen when the lock is set, or on any run while it is set (a lock from Marco's button or from
``/web_lock`` included), never counts again, for either window. Only newer events count. The id is kept in memory, as
is the time of the last 10-minute notice, so after a restart while unlocked the events of the last 24 hours count
again: the lock may be set once more and the notice may repeat. That errs on the side of the lock, and Marco lifts it
with ``/web_unlock``.

The notice holds a number and a time only: no code, username, address or digest, and nothing is logged here (W-13,
W-15).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Final, Protocol

from app.core import settings_text

if TYPE_CHECKING:
    from datetime import datetime

WINDOW: Final = timedelta(minutes=10)
THRESHOLD: Final = 5
LOCK_WINDOW: Final = timedelta(hours=24)
LOCK_THRESHOLD: Final = 15


class EventSource(Protocol):
    """The security events (``PgSecurityEvents``)."""

    async def refused_codes(self, since: datetime, after_id: int) -> int:
        """Sum of ``count`` of the ``code_refused`` events newer than ``since`` with an id above ``after_id``."""
        ...

    async def newest_id(self) -> int:
        """The highest event id of any kind; 0 when there are no events."""
        ...


class LockPort(Protocol):
    """``web_auth.web_lock`` (``PgWebLock``)."""

    async def is_locked(self) -> bool:
        """Whether the lock is set."""
        ...

    async def lock(self, now: datetime) -> bool:
        """Set the lock; ``True`` when this call set it."""
        ...


class Say(Protocol):
    """A plain note to Marco."""

    async def say(self, text: str) -> None:
        """Send it."""
        ...


class CodeAlert:
    """Sends the wrong-code notice and sets the lock."""

    def __init__(self, events: EventSource, lock: LockPort, chat: Say) -> None:
        """Wire the events, the lock and Telegram."""
        self._events = events
        self._lock = lock
        self._chat = chat
        self._noticed_at: datetime | None = None
        self._spent = 0  # events with an id up to this one never count again
        self._owed: tuple[int, datetime] | None = None  # a lock notice that could not be sent yet

    async def run(self, now: datetime) -> None:
        """Lock and say so at 15 wrong codes in 24 hours, else notify at 5 in 10 minutes; do nothing while locked."""
        if await self._lock.is_locked():
            self._spent = max(self._spent, await self._events.newest_id())
            await self._send_owed()
            return
        self._owed = None  # an unlock came before the notice could be sent: it would be stale
        day = await self._events.refused_codes(now - LOCK_WINDOW, self._spent)
        if day >= LOCK_THRESHOLD:
            newest = await self._events.newest_id()
            await self._lock.lock(now)
            self._spent = newest
            self._noticed_at = now
            self._owed = (day, now)
            await self._send_owed()
            return
        await self._alert(now)

    async def _send_owed(self) -> None:
        if self._owed is None:
            return
        count, at = self._owed
        await self._chat.say(settings_text.code_lock_alert(count, at))
        self._owed = None

    async def _alert(self, now: datetime) -> None:
        if self._noticed_at is not None and now - self._noticed_at < WINDOW:
            return
        count = await self._events.refused_codes(now - WINDOW, self._spent)
        if count < THRESHOLD:
            return
        await self._chat.say(settings_text.code_alert(count, now))
        self._noticed_at = now
