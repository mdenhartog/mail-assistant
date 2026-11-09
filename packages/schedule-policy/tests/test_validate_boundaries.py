from datetime import UTC, time

import pytest

from schedule_policy.policy import validate
from schedule_policy.testing import make_policy

START = time(23, 0)
END = time(7, 0)


@pytest.mark.parametrize("field", ["overview_at", "remind_at"])
def test_given_a_time_exactly_at_the_window_start_when_validated_then_refused(field):
    problems = validate(make_policy(**{field: START}))

    assert [p.rule for p in problems] == [f"{field.removesuffix('_at')}_in_quiet_hours"]


@pytest.mark.parametrize("field", ["overview_at", "remind_at"])
def test_given_a_time_exactly_at_the_window_end_when_validated_then_valid(field):
    assert validate(make_policy(**{field: END})) == []


@pytest.mark.parametrize("field", ["overview_at", "remind_at"])
def test_given_a_time_one_minute_before_the_start_or_after_the_end_when_validated_then_valid(field):
    assert validate(make_policy(**{field: time(22, 59)})) == []
    assert validate(make_policy(**{field: time(7, 1)})) == []


@pytest.mark.parametrize("field", ["overview_at", "remind_at"])
def test_given_a_time_one_minute_after_the_start_or_before_the_end_when_validated_then_refused(field):
    assert len(validate(make_policy(**{field: time(23, 1)}))) == 1
    assert len(validate(make_policy(**{field: time(6, 59)}))) == 1


def test_given_a_reminder_default_inside_the_window_when_validated_then_refused_with_a_move_to_the_end():
    (problem,) = validate(make_policy(remind_at=time(3, 0)))

    assert problem.rule == "remind_in_quiet_hours"
    assert problem.value == "03:00"
    assert problem.example == "Try 07:00"


def test_given_a_same_day_window_when_a_time_is_at_its_edges_then_start_is_inside_and_end_is_outside():
    window = {"quiet_start": time(7, 0), "quiet_end": time(19, 0)}

    assert [p.rule for p in validate(make_policy(overview_at=time(7, 0), remind_at=time(20, 0), **window))] == [
        "overview_in_quiet_hours"
    ]
    assert validate(make_policy(overview_at=time(19, 0), remind_at=time(20, 0), **window)) == []


@pytest.mark.parametrize(
    ("start", "end"), [(time(7, 0), time(8, 0)), (time(23, 0), time(0, 0)), (time(0, 0), time(12, 0))]
)
def test_given_the_edge_windows_when_validated_then_both_edges_are_checked_in_clock_minutes(start, end):
    inside = validate(make_policy(quiet_start=start, quiet_end=end, overview_at=start, remind_at=end))

    assert [p.rule for p in inside] == ["overview_in_quiet_hours"]


@pytest.mark.parametrize("minutes", [59, 60, 720, 721])
def test_given_a_window_of_59_60_720_or_721_minutes_when_validated_then_only_60_to_720_is_valid(minutes):
    start = time(8, 0)
    total = 8 * 60 + minutes
    end = time(total // 60 % 24, total % 60)

    problems = validate(make_policy(quiet_start=start, quiet_end=end, overview_at=time(5, 0), remind_at=time(5, 30)))

    assert (problems == []) is (60 <= minutes <= 720)
    if problems:
        assert [p.rule for p in problems] == ["quiet_window_length"]


@pytest.mark.parametrize("zone", ["Europe/Paris", "UTC", "America/Argentina/Buenos_Aires", "Pacific/Kiritimati"])
def test_given_a_known_iana_zone_when_validated_then_valid(zone):
    assert validate(make_policy(zone=zone)) == []


@pytest.mark.parametrize(
    "zone",
    [
        "Mars/Olympus",
        "",
        "europe/paris ",
        "../etc/passwd",
        "/etc/passwd",
        "Europe/../Paris",
        "C:\\Windows",
        "x" * 300,
        "UTC\x00",
        "Europe//Paris",
        "localtime",
        "Europe/Paris\n",
    ],
)
def test_given_an_unknown_or_path_like_zone_when_validated_then_refused(zone):
    problems = validate(make_policy(zone=zone))

    assert [p.rule for p in problems] == ["zone_unknown"]
    assert problems[0].example == "Try Europe/Amsterdam"


def test_given_a_time_with_seconds_when_validated_then_refused_as_not_whole_minutes():
    problems = validate(make_policy(overview_at=time(18, 0, 30)))

    assert [p.rule for p in problems] == ["time_not_whole_minute"]
    assert problems[0].value == "18:00:30"


def test_given_a_time_with_microseconds_when_validated_then_refused_as_not_whole_minutes():
    problems = validate(make_policy(remind_at=time(9, 0, 0, 5)))

    assert [p.rule for p in problems] == ["time_not_whole_minute"]


def test_given_a_time_with_a_zone_attached_when_validated_then_refused():
    problems = validate(make_policy(remind_at=time(9, 0, tzinfo=UTC)))

    assert [p.rule for p in problems] == ["time_has_zone"]


def test_given_several_broken_rules_when_validated_then_all_are_reported():
    problems = validate(
        make_policy(zone="Mars/Olympus", quiet_start=time(7, 0), quiet_end=time(7, 0), overview_at=time(7, 0))
    )

    assert sorted(p.rule for p in problems) == ["quiet_window_empty", "zone_unknown"]
