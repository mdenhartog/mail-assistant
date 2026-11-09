"""Times the agent keeps (spec C7, INT-002). Pure logic: the caller hands in "now" and the policy."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from schedule_policy.policy import TimePolicy

MIN_SNOOZE_HOURS = 1
MAX_SNOOZE_HOURS = 168


class InvalidSnoozeError(ValueError):
    """The requested snooze is not a number of hours between 1 and 168, or "tomorrow"."""


def _local(moment: datetime, policy: TimePolicy) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("a time zone is required")
    return moment.astimezone(ZoneInfo(policy.zone))


def _at(day: date, clock: time, policy: TimePolicy) -> datetime:
    return datetime.combine(day, clock, tzinfo=ZoneInfo(policy.zone))


def _next_at(now: datetime, clock: time, policy: TimePolicy) -> datetime:
    """The next moment the local clock shows ``clock``, strictly after ``now``."""
    local = _local(now, policy)
    candidate = _at(local.date(), clock, policy)
    return candidate if candidate > local else _at(local.date() + timedelta(days=1), clock, policy)


def in_quiet_hours(now: datetime, policy: TimePolicy) -> bool:
    """True from the quiet start up to, not including, the quiet end, in the policy's zone."""
    return policy.is_quiet(_local(now, policy).time())


def next_quiet_end(now: datetime, policy: TimePolicy) -> datetime:
    """The next quiet end after ``now``."""
    return _next_at(now, policy.quiet_end, policy)


def next_overview(now: datetime, policy: TimePolicy) -> datetime:
    """The next overview time strictly after ``now``."""
    return _next_at(now, policy.overview_at, policy)


def remind_due(now: datetime, amount: int | Literal["tomorrow"], policy: TimePolicy) -> datetime:
    """When a snoozed alert is due: in a number of hours, or the next day at the remind time."""
    local = _local(now, policy)
    if amount == "tomorrow":
        return _at(local.date() + timedelta(days=1), policy.remind_at, policy)
    if isinstance(amount, bool) or not MIN_SNOOZE_HOURS <= amount <= MAX_SNOOZE_HOURS:
        raise InvalidSnoozeError(f"hours must be between {MIN_SNOOZE_HOURS} and {MAX_SNOOZE_HOURS}, or 'tomorrow'")
    return now + timedelta(hours=amount)
