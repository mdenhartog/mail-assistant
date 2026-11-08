"""Times the agent keeps (spec C7). Pure logic: the caller hands in "now".

Quiet hours (23:00-07:00), the daily overview (18:00), the snooze default for "tomorrow" (09:00) and the time zone
(Europe/Amsterdam) are constants on purpose for the first release; making them adjustable is a later intent (INT-002).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

TIME_ZONE = ZoneInfo("Europe/Amsterdam")
QUIET_START = time(23, 0)
QUIET_END = time(7, 0)
OVERVIEW_AT = time(18, 0)
TOMORROW_AT = time(9, 0)
MIN_SNOOZE_HOURS = 1
MAX_SNOOZE_HOURS = 168


class InvalidSnoozeError(ValueError):
    """The requested snooze is not a number of hours between 1 and 168, or "tomorrow"."""


def _local(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("a time zone is required")
    return moment.astimezone(TIME_ZONE)


def _at(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, tzinfo=TIME_ZONE)


def _next_at(now: datetime, clock: time) -> datetime:
    """The next moment the local clock shows ``clock``, strictly after ``now``."""
    local = _local(now)
    candidate = _at(local.date(), clock)
    return candidate if candidate > local else _at(local.date() + timedelta(days=1), clock)


def in_quiet_hours(now: datetime) -> bool:
    """True from 23:00 up to, not including, 07:00 local time."""
    clock = _local(now).time()
    return clock >= QUIET_START or clock < QUIET_END


def next_quiet_end(now: datetime) -> datetime:
    """The next 07:00 local time after ``now``."""
    return _next_at(now, QUIET_END)


def next_overview(now: datetime) -> datetime:
    """The next 18:00 local time strictly after ``now``."""
    return _next_at(now, OVERVIEW_AT)


def snooze_due(now: datetime, amount: int | Literal["tomorrow"]) -> datetime:
    """When a snoozed alert is due: in a number of hours, or the next day at 09:00 local time."""
    local = _local(now)
    if amount == "tomorrow":
        return _at(local.date() + timedelta(days=1), TOMORROW_AT)
    if isinstance(amount, bool) or not MIN_SNOOZE_HOURS <= amount <= MAX_SNOOZE_HOURS:
        raise InvalidSnoozeError(f"hours must be between {MIN_SNOOZE_HOURS} and {MAX_SNOOZE_HOURS}, or 'tomorrow'")
    return (now + timedelta(hours=amount)).astimezone(TIME_ZONE)
