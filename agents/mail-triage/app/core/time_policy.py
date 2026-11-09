"""Times the agent keeps (spec C7, C-5, ADR-0027). Pure logic: the caller hands in "now" and the policy.

Every moment that leaves this module is in UTC and every comparison is between UTC moments. A wall time that does not
exist on a day (clock moved forward) resolves to the first valid moment after the gap; a wall time that occurs twice
(clock moved back) resolves to its first occurrence. A quiet window runs from its start to its end in clock time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from itertools import count
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from schedule_policy.policy import TimePolicy

MIN_SNOOZE_HOURS = 1
MAX_SNOOZE_HOURS = 168
_ONE_DAY = timedelta(days=1)


class InvalidSnoozeError(ValueError):
    """The requested snooze is not a number of hours between 1 and 168, or "tomorrow"."""


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("a time zone is required")
    return moment.astimezone(UTC)


def local_day(moment: datetime, policy: TimePolicy) -> date:
    """The calendar day of ``moment`` in the policy's zone."""
    return _utc(moment).astimezone(ZoneInfo(policy.zone)).date()


def _first_moment_after_gap(early: datetime, late: datetime, zone: ZoneInfo) -> datetime:
    """Walk minute by minute from ``early`` (old offset) to the clock change that gives ``late`` its new offset.

    The walk ends at the latest on ``late`` itself. Every clock change in the IANA data falls on a whole minute.
    """
    new_offset = late.astimezone(zone).utcoffset()
    probes = (early + timedelta(minutes=minute) for minute in count())
    return next(probe for probe in probes if probe.astimezone(zone).utcoffset() == new_offset)


def _moment_on(day: date, clock: time, policy: TimePolicy) -> datetime:
    """The UTC moment the wall clock of ``policy.zone`` first shows ``clock`` on ``day`` (ADR-0027)."""
    zone = ZoneInfo(policy.zone)
    wall = datetime.combine(day, clock)
    earlier = wall.replace(tzinfo=zone, fold=1).astimezone(UTC)  # in a gap: the reading with the new offset
    moment = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)  # a doubled hour: the first occurrence
    if moment.astimezone(zone).replace(tzinfo=None) == wall:
        return moment
    return _first_moment_after_gap(earlier, moment, zone)


def _next_at(now: datetime, clock: time, policy: TimePolicy) -> datetime:
    """The next moment the local clock shows ``clock``, strictly after ``now``."""
    moment = _utc(now)
    today = local_day(moment, policy)
    candidate = _moment_on(today, clock, policy)
    return candidate if candidate > moment else _moment_on(today + _ONE_DAY, clock, policy)


def day_start(day: date, policy: TimePolicy) -> datetime:
    """The first valid moment of a local day (01:00 when a clock change skips midnight)."""
    return _moment_on(day, time(0, 0), policy)


def overview_on(day: date, policy: TimePolicy) -> datetime:
    """The moment the overview is due on a local day."""
    return _moment_on(day, policy.overview_at, policy)


def in_quiet_hours(now: datetime, policy: TimePolicy) -> bool:
    """True from the quiet start up to, not including, the quiet end, in the policy's zone."""
    moment = _utc(now)
    if policy.window_minutes == 0:
        return False
    today = local_day(moment, policy)
    for day in (today - _ONE_DAY, today):  # the window that began yesterday evening, and today's
        end_day = day if policy.quiet_start < policy.quiet_end else day + _ONE_DAY
        if _moment_on(day, policy.quiet_start, policy) <= moment < _moment_on(end_day, policy.quiet_end, policy):
            return True
    return False


def next_quiet_end(now: datetime, policy: TimePolicy) -> datetime:
    """The next quiet end after ``now``."""
    return _next_at(now, policy.quiet_end, policy)


def next_overview(now: datetime, policy: TimePolicy) -> datetime:
    """The next overview time strictly after ``now``."""
    return _next_at(now, policy.overview_at, policy)


def remind_due(now: datetime, amount: int | Literal["tomorrow"], policy: TimePolicy) -> datetime:
    """When a snoozed alert is due: in a number of hours, or the next day at the remind time."""
    moment = _utc(now)
    if amount == "tomorrow":
        return _moment_on(local_day(moment, policy) + _ONE_DAY, policy.remind_at, policy)
    if isinstance(amount, bool) or not MIN_SNOOZE_HOURS <= amount <= MAX_SNOOZE_HOURS:
        raise InvalidSnoozeError(f"hours must be between {MIN_SNOOZE_HOURS} and {MAX_SNOOZE_HOURS}, or 'tomorrow'")
    return moment + timedelta(hours=amount)
