from datetime import time

import pytest

from schedule_policy.policy import DEFAULT_POLICY, validate


def test_given_the_defaults_when_validated_then_there_are_no_problems():
    assert validate(DEFAULT_POLICY) == []


def test_given_the_defaults_when_read_then_they_match_the_first_release():
    assert DEFAULT_POLICY.zone == "Europe/Amsterdam"
    assert (DEFAULT_POLICY.quiet_start, DEFAULT_POLICY.quiet_end) == (time(23, 0), time(7, 0))
    assert (DEFAULT_POLICY.overview_at, DEFAULT_POLICY.remind_at) == (time(18, 0), time(9, 0))


def test_given_a_policy_when_changed_in_place_then_it_is_refused():
    with pytest.raises(AttributeError):
        DEFAULT_POLICY.zone = "UTC"  # type: ignore[misc]
