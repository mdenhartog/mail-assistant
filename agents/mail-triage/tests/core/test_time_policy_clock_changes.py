"""U-quiet-hours-03: clock changes follow ADR-0027 (spec C-5, AC-28).

A time that does not exist on a day means the first valid moment after the gap; a time that occurs twice means its
first occurrence; a quiet window is counted in clock minutes. Every expectation below is a UTC moment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.core.time_policy import (
    day_start,
    in_quiet_hours,
    local_day,
    next_overview,
    next_quiet_end,
    overview_on,
    remind_due,
)
from schedule_policy.policy import validate
from schedule_policy.testing import make_policy

MINUTE = timedelta(minutes=1)


def utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Change:
    """One clock-change day: the zone, the wall time that is affected and where the moments fall."""

    zone: str
    wall: time  # the configured wall time that falls in the gap, or occurs twice
    eve: datetime  # a moment around noon on the local day before the change day
    before: datetime  # a moment earlier on the change day (or the eve when the wall time is late in the day)
    first: datetime  # the transition moment (gap) or the first occurrence of ``wall`` (doubled hour)
    next_day: datetime  # the same wall time on the following local day


GAPS = [
    pytest.param(
        Change(
            "Europe/Amsterdam",
            time(2, 30),
            utc("2026-03-28T11:00"),
            utc("2026-03-28T11:00"),
            utc("2026-03-29T01:00"),
            utc("2026-03-30T00:30"),
        ),
        id="amsterdam-spring",
    ),
    pytest.param(
        Change(
            "America/New_York",
            time(2, 30),
            utc("2026-03-07T17:00"),
            utc("2026-03-07T17:00"),
            utc("2026-03-08T07:00"),
            utc("2026-03-09T06:30"),
        ),
        id="new-york-spring",
    ),
    pytest.param(
        Change(
            "America/Santiago",
            time(0, 30),
            utc("2026-09-05T16:00"),
            utc("2026-09-05T16:00"),
            utc("2026-09-06T04:00"),
            utc("2026-09-07T03:30"),
        ),
        id="santiago-spring-midnight",
    ),
]

DOUBLED = [
    pytest.param(
        Change(
            "Europe/Amsterdam",
            time(2, 30),
            utc("2026-10-24T11:00"),
            utc("2026-10-24T11:00"),
            utc("2026-10-25T00:30"),
            utc("2026-10-26T01:30"),
        ),
        id="amsterdam-autumn",
    ),
    pytest.param(
        Change(
            "America/New_York",
            time(1, 30),
            utc("2026-10-31T16:00"),
            utc("2026-10-31T16:00"),
            utc("2026-11-01T05:30"),
            utc("2026-11-02T06:30"),
        ),
        id="new-york-autumn",
    ),
    pytest.param(
        Change(
            "America/Santiago",
            time(23, 30),
            utc("2026-04-03T14:00"),
            utc("2026-04-04T14:00"),
            utc("2026-04-05T02:30"),
            utc("2026-04-06T03:30"),
        ),
        id="santiago-autumn-midnight",
    ),
]


def _shifted(clock: time, hours: int) -> time:
    return (datetime.combine(date(2000, 1, 1), clock) + timedelta(hours=hours)).time()


@pytest.mark.parametrize("change", [*GAPS, *DOUBLED])
def test_given_a_wall_time_on_a_clock_change_day_when_asked_then_overview_end_and_remind_follow_adr_0027(
    change: Change,
) -> None:
    policy = make_policy(
        zone=change.zone,
        quiet_start=_shifted(change.wall, -5),
        quiet_end=change.wall,
        overview_at=change.wall,
        remind_at=change.wall,
    )

    assert next_overview(change.before, policy) == change.first
    assert next_quiet_end(change.before, policy) == change.first
    assert remind_due(change.eve, "tomorrow", policy) == change.first
    # once that moment has passed, the next one is on the following day (never the second occurrence)
    assert next_overview(change.first + MINUTE, policy) == change.next_day
    assert next_quiet_end(change.first + MINUTE, policy) == change.next_day
    assert remind_due(change.first + MINUTE, "tomorrow", policy) == change.next_day


@pytest.mark.parametrize("change", GAPS)
def test_given_quiet_hours_that_end_or_start_in_a_gap_when_asked_then_the_change_moment_is_the_edge(
    change: Change,
) -> None:
    ends_in_gap = make_policy(zone=change.zone, quiet_start=_shifted(change.wall, -5), quiet_end=change.wall)
    starts_in_gap = make_policy(zone=change.zone, quiet_start=change.wall, quiet_end=_shifted(change.wall, 4))

    assert in_quiet_hours(change.first - MINUTE, ends_in_gap)
    assert not in_quiet_hours(change.first, ends_in_gap)
    assert not in_quiet_hours(change.first - MINUTE, starts_in_gap)
    assert in_quiet_hours(change.first, starts_in_gap)


@pytest.mark.parametrize("change", DOUBLED)
def test_given_quiet_hours_that_end_in_a_doubled_hour_when_asked_then_the_first_occurrence_is_the_end(
    change: Change,
) -> None:
    policy = make_policy(zone=change.zone, quiet_start=_shifted(change.wall, -5), quiet_end=change.wall)

    assert in_quiet_hours(change.first - MINUTE, policy)
    assert not in_quiet_hours(change.first, policy)
    assert not in_quiet_hours(change.first + 40 * MINUTE, policy)  # the clock shows a time before the end again
    assert not in_quiet_hours(change.first + 60 * MINUTE, policy)  # the second occurrence of the end time


@pytest.mark.parametrize("change", DOUBLED)
def test_given_quiet_hours_that_start_in_a_doubled_hour_when_asked_then_the_first_occurrence_is_the_start(
    change: Change,
) -> None:
    policy = make_policy(zone=change.zone, quiet_start=change.wall, quiet_end=_shifted(change.wall, 4))

    assert not in_quiet_hours(change.first - MINUTE, policy)
    assert in_quiet_hours(change.first, policy)
    assert in_quiet_hours(change.first + 40 * MINUTE, policy)  # the clock shows a time before the start again
    assert in_quiet_hours(change.first + 60 * MINUTE, policy)  # the second occurrence of the start time


@pytest.mark.parametrize(
    ("zone", "start_utc", "end_utc"),
    [
        ("Europe/Amsterdam", utc("2026-10-24T18:00"), utc("2026-10-25T07:00")),  # 13 h in real time
        ("Europe/Amsterdam", utc("2026-03-28T19:00"), utc("2026-03-29T06:00")),  # 11 h in real time
        ("America/New_York", utc("2026-11-01T00:00"), utc("2026-11-01T13:00")),  # 13 h in real time
        ("America/New_York", utc("2026-03-08T01:00"), utc("2026-03-08T12:00")),  # 11 h in real time
    ],
    ids=["amsterdam-25h", "amsterdam-23h", "new-york-25h", "new-york-23h"],
)
def test_given_a_12_hour_window_on_a_23_or_25_hour_day_when_validated_and_asked_then_both_agree(
    zone: str, start_utc: datetime, end_utc: datetime
) -> None:
    policy = make_policy(zone=zone, quiet_start=time(20, 0), quiet_end=time(8, 0))

    assert validate(policy) == []  # 12 clock hours, whatever the elapsed time of the night
    assert not in_quiet_hours(start_utc - MINUTE, policy)
    assert in_quiet_hours(start_utc, policy)
    assert in_quiet_hours(end_utc - MINUTE, policy)
    assert not in_quiet_hours(end_utc, policy)


@pytest.mark.parametrize(
    ("zone", "day", "midnight"),
    [
        ("Europe/Amsterdam", date(2026, 11, 9), utc("2026-11-08T23:00")),
        ("Europe/Amsterdam", date(2026, 3, 29), utc("2026-03-28T23:00")),
        ("America/Santiago", date(2026, 9, 6), utc("2026-09-06T04:00")),  # midnight does not exist: 01:00 local
        ("America/Santiago", date(2026, 4, 5), utc("2026-04-05T04:00")),
        ("Asia/Kathmandu", date(2026, 11, 9), utc("2026-11-08T18:15")),
    ],
)
def test_given_a_day_when_its_start_is_asked_then_it_is_the_first_valid_midnight_moment(
    zone: str, day: date, midnight: datetime
) -> None:
    assert day_start(day, make_policy(zone=zone)) == midnight


def test_given_an_empty_window_when_asked_then_it_is_never_quiet() -> None:
    empty = make_policy(quiet_start=time(7, 0), quiet_end=time(7, 0))

    assert not any(in_quiet_hours(utc("2026-11-09T00:00") + timedelta(hours=hour), empty) for hour in range(48))


def test_given_a_moment_near_midnight_when_its_local_day_is_asked_then_the_policy_zone_decides() -> None:
    moment = utc("2026-11-09T23:30")

    assert local_day(moment, make_policy(zone="Europe/Amsterdam")) == date(2026, 11, 10)
    assert local_day(moment, make_policy(zone="America/New_York")) == date(2026, 11, 9)


def test_given_a_day_when_its_overview_moment_is_asked_then_the_clock_change_rule_applies() -> None:
    policy = make_policy(zone="Europe/Amsterdam", overview_at=time(2, 30))

    assert overview_on(date(2026, 3, 29), policy) == utc("2026-03-29T01:00")  # 02:30 does not exist: 03:00
    assert overview_on(date(2026, 11, 9), make_policy()) == utc("2026-11-09T17:00")  # 18:00 in winter time


def test_given_a_half_hour_gap_when_a_time_inside_it_is_asked_then_it_is_the_end_of_that_gap() -> None:
    lord_howe = make_policy(zone="Australia/Lord_Howe", overview_at=time(2, 15))  # 02:00 jumps to 02:30

    assert overview_on(date(2026, 10, 4), lord_howe) == utc("2026-10-03T15:30")
    assert overview_on(date(2026, 10, 5), lord_howe) == utc("2026-10-04T15:15")  # a normal day: 02:15 at UTC+11
