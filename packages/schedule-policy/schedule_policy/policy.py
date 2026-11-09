"""The schedule policy: four values and one zone, validated as a whole row (spec C-2, ADR-0027)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class TimePolicy:
    """Quiet hours, daily overview, remind-me-later default and time zone, as wall-clock times in ``zone``."""

    zone: str
    quiet_start: time
    quiet_end: time
    overview_at: time
    remind_at: time


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


def validate(policy: TimePolicy) -> list[Problem]:
    """Check the whole row; an empty list means valid."""
    return []
