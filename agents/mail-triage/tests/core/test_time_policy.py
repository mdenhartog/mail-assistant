"""U-03: quiet hours, snooze and overview times (spec C7, AC-9, AC-31, AC-32)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.time_policy import (
    InvalidSnoozeError,
    in_quiet_hours,
    next_overview,
    next_quiet_end,
    remind_due,
)
from schedule_policy.policy import DEFAULT_POLICY

AMS = ZoneInfo("Europe/Amsterdam")


def local(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=AMS)


def test_given_23_30_local_when_asked_then_quiet_hours_end_at_07_00_next_day() -> None:
    now = local(2026, 11, 9, 23, 30)

    assert in_quiet_hours(now, DEFAULT_POLICY)
    assert next_quiet_end(now, DEFAULT_POLICY) == local(2026, 11, 10, 7)


def test_given_03_00_local_when_asked_then_quiet_hours_end_at_07_00_the_same_day() -> None:
    now = local(2026, 11, 10, 3)

    assert in_quiet_hours(now, DEFAULT_POLICY)
    assert next_quiet_end(now, DEFAULT_POLICY) == local(2026, 11, 10, 7)


@pytest.mark.parametrize(("hour", "minute", "quiet"), [(7, 0, False), (6, 59, True), (22, 59, False), (23, 0, True)])
def test_given_the_edges_of_quiet_hours_when_asked_then_07_00_is_open_and_23_00_is_quiet(
    hour: int, minute: int, quiet: bool
) -> None:
    assert in_quiet_hours(local(2026, 11, 10, hour, minute), DEFAULT_POLICY) is quiet


def test_given_a_time_in_utc_when_asked_then_it_is_judged_in_amsterdam_time() -> None:
    assert in_quiet_hours(datetime(2026, 11, 9, 22, 30, tzinfo=UTC), DEFAULT_POLICY)  # 23:30 in Amsterdam (winter time)
    assert not in_quiet_hours(
        datetime(2026, 7, 9, 20, 30, tzinfo=UTC), DEFAULT_POLICY
    )  # 22:30 in Amsterdam (summer time)


@pytest.mark.parametrize(
    ("night", "end_utc_hour"),
    [
        ((2026, 10, 24), 6),  # clocks go back on 25 October: 07:00 local is 06:00 UTC
        ((2026, 3, 28), 5),  # clocks go forward on 29 March: 07:00 local is 05:00 UTC
    ],
)
def test_given_a_daylight_saving_night_when_quiet_hours_end_then_it_is_07_00_local_time(
    night: tuple[int, int, int], end_utc_hour: int
) -> None:
    end = next_quiet_end(local(*night, 23, 30), DEFAULT_POLICY)

    assert (end.astimezone(AMS).hour, end.astimezone(AMS).minute) == (7, 0)
    assert end.astimezone(UTC).hour == end_utc_hour


def test_given_tomorrow_at_15_00_when_snoozing_then_it_is_due_the_next_day_at_09_00_local() -> None:
    assert remind_due(local(2026, 11, 9, 15), "tomorrow", DEFAULT_POLICY) == local(2026, 11, 10, 9)


def test_given_a_number_of_hours_when_snoozing_then_it_is_due_that_many_hours_later() -> None:
    now = local(2026, 11, 9, 15)

    assert remind_due(now, 3, DEFAULT_POLICY).astimezone(UTC) == datetime(2026, 11, 9, 17, 0, tzinfo=UTC)


@pytest.mark.parametrize("hours", [0, -1, 169])
def test_given_hours_outside_1_to_168_when_snoozing_then_it_is_rejected(hours: int) -> None:
    with pytest.raises(InvalidSnoozeError):
        remind_due(local(2026, 11, 9, 15), hours, DEFAULT_POLICY)


def test_given_the_overview_time_when_asked_then_it_is_the_next_18_00_strictly_after_now() -> None:
    assert next_overview(local(2026, 11, 9, 17, 59), DEFAULT_POLICY) == local(2026, 11, 9, 18)
    assert next_overview(local(2026, 11, 9, 18), DEFAULT_POLICY) == local(2026, 11, 10, 18)


def test_given_a_time_without_time_zone_when_asked_then_it_is_rejected() -> None:
    naive = datetime(2026, 11, 9, 12, 0)  # noqa: DTZ001

    with pytest.raises(ValueError, match="time zone"):
        in_quiet_hours(naive, DEFAULT_POLICY)
