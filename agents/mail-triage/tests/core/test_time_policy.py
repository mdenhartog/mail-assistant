"""U-03: quiet hours, snooze and overview times (spec C7, AC-9, AC-31, AC-32)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
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
from schedule_policy.testing import make_policy

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


def at_zone(zone: str, iso: str, *, fold: int = 0) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo(zone), fold=fold)


NIGHT_OWL = make_policy(quiet_start=time(1, 0), quiet_end=time(6, 0))  # the window sits inside one calendar day


@pytest.mark.parametrize(("hour", "minute", "quiet"), [(23, 30, False), (3, 0, True), (6, 0, False), (1, 0, True)])
def test_given_quiet_hours_01_00_to_06_00_when_asked_then_23_30_is_open_03_00_quiet_and_06_00_open(
    hour: int, minute: int, quiet: bool
) -> None:
    assert in_quiet_hours(local(2026, 11, 10, hour, minute), NIGHT_OWL) is quiet


def test_given_new_york_with_23_00_to_07_00_when_it_is_23_30_there_then_it_is_quiet() -> None:
    new_york = make_policy(zone="America/New_York")

    assert in_quiet_hours(at_zone("America/New_York", "2026-11-09T23:30"), new_york)
    assert not in_quiet_hours(at_zone("America/New_York", "2026-11-09T22:30"), new_york)


def test_given_the_exact_quiet_start_and_end_when_asked_then_quiet_from_the_start_and_open_at_the_end() -> None:
    assert in_quiet_hours(local(2026, 11, 9, 23), DEFAULT_POLICY)
    assert not in_quiet_hours(local(2026, 11, 9, 23) - timedelta(seconds=1), DEFAULT_POLICY)
    assert in_quiet_hours(local(2026, 11, 10, 7) - timedelta(seconds=1), DEFAULT_POLICY)
    assert not in_quiet_hours(local(2026, 11, 10, 7), DEFAULT_POLICY)


def test_given_a_moment_without_time_zone_when_any_function_is_asked_then_it_is_rejected() -> None:
    naive = datetime(2026, 11, 9, 12, 0)  # noqa: DTZ001

    for call in (
        lambda: in_quiet_hours(naive, DEFAULT_POLICY),
        lambda: next_quiet_end(naive, DEFAULT_POLICY),
        lambda: next_overview(naive, DEFAULT_POLICY),
        lambda: remind_due(naive, 2, DEFAULT_POLICY),
        lambda: remind_due(naive, "tomorrow", DEFAULT_POLICY),
    ):
        with pytest.raises(ValueError, match="time zone"):
            call()


def test_given_a_moment_in_another_zone_when_asked_then_the_policy_zone_decides() -> None:
    tokyo_morning = at_zone("Asia/Tokyo", "2026-11-10T07:30")  # 23:30 in Amsterdam the evening before

    assert in_quiet_hours(tokyo_morning, DEFAULT_POLICY)
    assert next_quiet_end(tokyo_morning, DEFAULT_POLICY) == local(2026, 11, 10, 7)


def test_given_two_policies_of_different_zones_when_one_function_is_called_then_each_uses_its_own_zone() -> None:
    new_york = make_policy(zone="America/New_York")
    now = datetime(2026, 11, 10, 4, 30, tzinfo=UTC)  # 05:30 Amsterdam, 23:30 New York (previous day)

    assert next_quiet_end(now, DEFAULT_POLICY) == datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    assert next_quiet_end(now, new_york) == datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    assert next_quiet_end(now, DEFAULT_POLICY) == datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    assert in_quiet_hours(now, DEFAULT_POLICY)
    assert in_quiet_hours(now, new_york)


@pytest.mark.parametrize(
    ("zone", "offset"),
    [("Asia/Kolkata", timedelta(hours=5, minutes=30)), ("Asia/Kathmandu", timedelta(hours=5, minutes=45))],
)
def test_given_a_zone_with_a_part_hour_offset_when_asked_then_wall_clock_times_are_exact(
    zone: str, offset: timedelta
) -> None:
    policy = make_policy(zone=zone)
    start_utc = datetime(2026, 11, 9, 23, 0, tzinfo=UTC) - offset  # 23:00 local

    assert not in_quiet_hours(start_utc - timedelta(minutes=1), policy)
    assert in_quiet_hours(start_utc, policy)
    assert next_quiet_end(start_utc, policy) == datetime(2026, 11, 10, 7, 0, tzinfo=UTC) - offset
    assert next_overview(start_utc, policy) == datetime(2026, 11, 10, 18, 0, tzinfo=UTC) - offset
    assert remind_due(start_utc, "tomorrow", policy) == datetime(2026, 11, 10, 9, 0, tzinfo=UTC) - offset


def test_given_sydney_whose_clocks_change_in_october_and_april_when_asked_then_the_offset_of_the_day_is_used() -> None:
    policy = make_policy(zone="Australia/Sydney")
    summer = at_zone("Australia/Sydney", "2026-12-01T03:00")  # UTC+11
    winter = at_zone("Australia/Sydney", "2026-07-01T03:00")  # UTC+10

    assert in_quiet_hours(summer, policy)
    assert in_quiet_hours(winter, policy)
    assert next_quiet_end(summer, policy) == datetime(2026, 11, 30, 20, 0, tzinfo=UTC)
    assert next_quiet_end(winter, policy) == datetime(2026, 6, 30, 21, 0, tzinfo=UTC)
