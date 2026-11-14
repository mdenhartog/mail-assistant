"""The schedule policy: four values and one zone, validated as a whole row (spec C-2, ADR-0027).

Times are wall-clock times in ``zone``. The quiet window starts inclusive and ends exclusive, as ``in_quiet_hours``
does today, and its length is counted in clock minutes, never in elapsed time (so a 23 h or 25 h day does not matter).
"""

# No "from __future__ import annotations" on purpose: evaluated annotations keep mutation testing honest.
from dataclasses import dataclass
from datetime import time
from functools import lru_cache
from importlib import resources

MINUTES_PER_DAY = 24 * 60
MIN_WINDOW_MINUTES = 60
MAX_WINDOW_MINUTES = 12 * 60
MAX_SHOWN_LENGTH = 64  # a refused zone text is echoed back at most this long

# Every rule id ``validate`` can report: a consumer that maps rules to fields checks its map against this list.
RULES: tuple[str, ...] = (
    "zone_unknown",
    "time_not_whole_minute",
    "time_has_zone",
    "quiet_window_empty",
    "quiet_window_length",
    "overview_in_quiet_hours",
    "remind_in_quiet_hours",
)


@dataclass(frozen=True, slots=True)
class TimePolicy:
    """Quiet hours, daily overview, remind-me-later default and time zone, as wall-clock times in ``zone``."""

    zone: str
    quiet_start: time
    quiet_end: time
    overview_at: time
    remind_at: time

    @property
    def window_minutes(self) -> int:
        """Length of the quiet window in clock minutes (0 when start equals end)."""
        return (_minute_of_day(self.quiet_end) - _minute_of_day(self.quiet_start)) % MINUTES_PER_DAY

    def is_quiet(self, clock: time) -> bool:
        """True from the quiet start up to, not including, the quiet end; never true for an empty window."""
        start, end, now = (_minute_of_day(t) for t in (self.quiet_start, self.quiet_end, clock))
        if start <= end:
            return start <= now < end
        return now >= start or now < end


@dataclass(frozen=True, slots=True)
class Problem:
    """A broken rule: its id, the value given and a working example."""

    rule: str
    value: str
    example: str


DEFAULT_POLICY = TimePolicy(
    zone="Europe/Amsterdam",
    quiet_start=time(23, 0),
    quiet_end=time(7, 0),
    overview_at=time(18, 0),
    remind_at=time(9, 0),
)


def _minute_of_day(clock: time) -> int:
    return clock.hour * 60 + clock.minute


def _hhmm(minutes: int) -> str:
    minutes %= MINUTES_PER_DAY
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _show(clock: time) -> str:
    if clock.second or clock.microsecond:
        return clock.isoformat()
    return _hhmm(_minute_of_day(clock))


@lru_cache(maxsize=1)
def _known_zones() -> frozenset[str]:
    # The list of the pinned ``tzdata`` package, not ``zoneinfo.available_timezones()``: that one also lists whatever
    # files the host keeps in /usr/share/zoneinfo (``localtime``, ``posixrules``), which are no IANA zones.
    return frozenset(resources.files("tzdata").joinpath("zones").read_text(encoding="utf-8").split())


def _zone_problems(zone: str) -> list[Problem]:
    # Membership in the IANA list is the whole check: a path, an empty name or a stray character is simply not in it.
    if zone in _known_zones():
        return []
    return [Problem("zone_unknown", zone[:MAX_SHOWN_LENGTH], f"Try {DEFAULT_POLICY.zone}")]


def _time_problems(policy: TimePolicy) -> list[Problem]:
    problems: list[Problem] = []
    for clock in (policy.quiet_start, policy.quiet_end, policy.overview_at, policy.remind_at):
        if clock.second or clock.microsecond:
            problems.append(Problem("time_not_whole_minute", _show(clock), f"Try {_hhmm(_minute_of_day(clock))}"))
        if clock.tzinfo is not None:
            problems.append(Problem("time_has_zone", _show(clock), f"Try {_hhmm(_minute_of_day(clock))}"))
    return problems


def _window_problems(policy: TimePolicy) -> list[Problem]:
    start, end = _minute_of_day(policy.quiet_start), _minute_of_day(policy.quiet_end)
    shown = f"{_hhmm(start)} to {_hhmm(end)}"
    length = policy.window_minutes
    if length == 0:
        return [Problem("quiet_window_empty", shown, f"Try {_hhmm(start)} to {_hhmm(start + MAX_WINDOW_MINUTES)}")]
    if length < MIN_WINDOW_MINUTES:
        return [Problem("quiet_window_length", shown, f"Try {_hhmm(start)} to {_hhmm(start + MIN_WINDOW_MINUTES)}")]
    if length > MAX_WINDOW_MINUTES:
        return [Problem("quiet_window_length", shown, f"Try {_hhmm(start)} to {_hhmm(start + MAX_WINDOW_MINUTES)}")]
    return []


def _outside_problems(policy: TimePolicy) -> list[Problem]:
    # An empty window is never quiet (``is_quiet``), so it needs no special case here.
    move_to = f"Try {_hhmm(_minute_of_day(policy.quiet_end))}"
    return [
        Problem(rule, _show(clock), move_to)
        for rule, clock in (
            ("overview_in_quiet_hours", policy.overview_at),
            ("remind_in_quiet_hours", policy.remind_at),
        )
        if policy.is_quiet(clock)
    ]


def validate(policy: TimePolicy) -> list[Problem]:
    """Check the whole row; an empty list means valid."""
    return [
        *_zone_problems(policy.zone),
        *_time_problems(policy),
        *_window_problems(policy),
        *_outside_problems(policy),
    ]
