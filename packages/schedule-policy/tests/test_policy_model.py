import dataclasses
from datetime import time

import pytest

from schedule_policy import policy as policy_module
from schedule_policy.policy import DEFAULT_POLICY, Problem, validate
from schedule_policy.testing import make_policy


def test_given_an_empty_window_when_refused_then_the_example_is_a_12_hour_window_from_the_start():
    (problem,) = validate(make_policy(quiet_start=time(22, 0), quiet_end=time(22, 0), overview_at=time(12, 0)))

    assert (problem.rule, problem.value, problem.example) == (
        "quiet_window_empty",
        "22:00 to 22:00",
        "Try 22:00 to 10:00",
    )


def test_given_a_too_long_window_when_refused_then_the_example_is_a_12_hour_window_from_the_start():
    (problem,) = validate(
        make_policy(quiet_start=time(5, 15), quiet_end=time(20, 0), overview_at=time(21, 0), remind_at=time(21, 30))
    )

    assert (problem.rule, problem.value, problem.example) == (
        "quiet_window_length",
        "05:15 to 20:00",
        "Try 05:15 to 17:15",
    )


def test_given_times_late_in_the_hour_when_shown_then_hours_and_minutes_are_exact():
    (problem,) = validate(make_policy(quiet_start=time(22, 59), quiet_end=time(23, 0), overview_at=time(12, 0)))

    assert problem.value == "22:59 to 23:00"
    assert problem.example == "Try 22:59 to 23:59"


def test_given_a_start_equal_to_the_end_when_asked_if_quiet_then_nothing_is_quiet():
    # A broken row must never silence the agent (spec goal 4), so an empty window covers no minute.
    policy = make_policy(quiet_start=time(7, 0), quiet_end=time(7, 0))

    assert not any(policy.is_quiet(time(h, 0)) for h in range(24))


def test_given_a_window_when_asked_at_its_edges_then_the_start_is_quiet_and_the_end_is_not():
    same_day = make_policy(quiet_start=time(7, 0), quiet_end=time(19, 0))
    overnight = make_policy(quiet_start=time(23, 0), quiet_end=time(7, 0))

    assert (same_day.is_quiet(time(7, 0)), same_day.is_quiet(time(18, 59)), same_day.is_quiet(time(19, 0))) == (
        True,
        True,
        False,
    )
    assert (overnight.is_quiet(time(23, 0)), overnight.is_quiet(time(6, 59)), overnight.is_quiet(time(7, 0))) == (
        True,
        True,
        False,
    )


def test_given_a_very_long_zone_text_when_refused_then_the_echoed_value_is_cut_to_64_characters():
    (problem,) = validate(make_policy(zone="x" * 300))

    assert problem.rule == "zone_unknown"
    assert problem.value == "x" * 64


def test_given_a_zone_text_of_exactly_64_characters_when_refused_then_it_is_echoed_whole():
    (problem,) = validate(make_policy(zone="y" * 64))

    assert problem.value == "y" * 64


def test_given_a_listed_zone_with_a_trailing_character_when_validated_then_refused():
    assert [p.rule for p in validate(make_policy(zone="UTC "))] == ["zone_unknown"]
    assert [p.rule for p in validate(make_policy(zone="utc"))] == ["zone_unknown"]


def test_given_the_value_objects_when_inspected_then_they_are_frozen_and_slotted():
    problem = Problem("r", "v", "e")

    for instance in (problem, DEFAULT_POLICY):
        assert not hasattr(instance, "__dict__")
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, dataclasses.fields(instance)[0].name, "other")


def test_given_the_zone_list_when_read_twice_then_it_is_built_once():
    first = policy_module._known_zones()

    assert policy_module._known_zones() is first
