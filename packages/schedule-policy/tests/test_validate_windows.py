from datetime import time

import pytest

from schedule_policy.policy import validate
from schedule_policy.testing import make_policy


def _window(start: time, end: time):
    return validate(make_policy(quiet_start=start, quiet_end=end, overview_at=time(20, 0), remind_at=time(21, 0)))


@pytest.mark.parametrize(
    ("start", "end"),
    [(time(23, 0), time(7, 0)), (time(7, 0), time(19, 0)), (time(7, 0), time(8, 0))],
)
def test_given_a_window_of_1_to_12_hours_when_validated_then_valid(start, end):
    assert _window(start, end) == []


@pytest.mark.parametrize(
    ("start", "end", "rule"),
    [
        (time(7, 0), time(19, 1), "quiet_window_length"),
        (time(7, 0), time(7, 30), "quiet_window_length"),
        (time(23, 0), time(23, 0), "quiet_window_empty"),
    ],
)
def test_given_a_bad_window_when_validated_then_refused_with_rule_value_and_example(start, end, rule):
    problems = _window(start, end)

    assert [p.rule for p in problems] == [rule]
    assert f"{start:%H:%M}" in problems[0].value
    assert f"{end:%H:%M}" in problems[0].value
    assert problems[0].example.startswith("Try ")


def test_given_a_13_hour_window_when_refused_then_the_example_is_a_valid_12_hour_window():
    (problem,) = _window(time(22, 0), time(11, 0))

    assert problem.example == "Try 22:00 to 10:00"


@pytest.mark.parametrize(
    ("start", "example"),
    [
        (time(1, 0), "Try 01:00 to 13:00"),
        (time(7, 0), "Try 07:00 to 19:00"),
        (time(10, 30), "Try 10:30 to 22:30"),
        (time(23, 0), "Try 23:00 to 11:00"),
    ],
)
def test_given_an_empty_window_when_refused_then_the_example_is_a_12_hour_window_from_the_same_start(start, example):
    (problem,) = _window(start, start)

    assert problem.rule == "quiet_window_empty"
    assert problem.example == example


def test_given_a_one_minute_window_with_the_overview_inside_when_validated_then_both_problems_are_reported():
    problems = validate(
        make_policy(quiet_start=time(7, 0), quiet_end=time(7, 1), overview_at=time(7, 0), remind_at=time(20, 0))
    )

    assert [p.rule for p in problems] == ["quiet_window_length", "overview_in_quiet_hours"]
    assert problems[1].example == "Try 07:01"


def test_given_an_empty_window_with_times_at_the_start_when_validated_then_only_the_empty_window_is_reported():
    problems = validate(
        make_policy(quiet_start=time(7, 0), quiet_end=time(7, 0), overview_at=time(7, 0), remind_at=time(7, 0))
    )

    assert [p.rule for p in problems] == ["quiet_window_empty"]


def test_given_a_too_short_window_when_refused_then_the_example_is_a_valid_1_hour_window():
    (problem,) = _window(time(7, 0), time(7, 30))

    assert problem.example == "Try 07:00 to 08:00"


@pytest.mark.parametrize(
    ("overview", "start", "end"),
    [(time(6, 0), time(23, 0), time(7, 0)), (time(18, 0), time(17, 0), time(3, 0))],
)
def test_given_an_overview_inside_the_window_when_validated_then_refused_with_a_move_outside(overview, start, end):
    problems = validate(make_policy(overview_at=overview, quiet_start=start, quiet_end=end))

    assert [p.rule for p in problems] == ["overview_in_quiet_hours"]
    assert f"{overview:%H:%M}" in problems[0].value
    assert problems[0].example == f"Try {end:%H:%M}"
