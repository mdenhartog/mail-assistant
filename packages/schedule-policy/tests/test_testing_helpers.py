from datetime import UTC, datetime, time, timedelta

import pytest

from schedule_policy.policy import DEFAULT_POLICY
from schedule_policy.testing import FakeClock, make_policy


def test_given_no_overrides_when_made_then_the_policy_is_the_default():
    assert make_policy() == DEFAULT_POLICY


def test_given_an_override_when_made_then_only_that_field_changes():
    policy = make_policy(overview_at=time(17, 0))

    assert policy.overview_at == time(17, 0)
    assert policy.zone == DEFAULT_POLICY.zone


def test_given_an_unknown_field_when_made_then_a_type_error_is_raised():
    with pytest.raises(TypeError):
        make_policy(colour="red")


def test_given_a_fake_clock_when_advanced_then_now_moves_only_then():
    start = datetime(2026, 3, 29, 0, 59, tzinfo=UTC)
    clock = FakeClock(start)

    assert clock.now() == start
    assert clock.advance(timedelta(minutes=2)) == datetime(2026, 3, 29, 1, 1, tzinfo=UTC)
    assert clock.now() == datetime(2026, 3, 29, 1, 1, tzinfo=UTC)


def test_given_a_fake_clock_when_set_then_now_jumps():
    clock = FakeClock()
    target = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)

    clock.set(target)

    assert clock.now() == target


def test_given_a_naive_moment_when_a_clock_is_made_or_set_then_it_is_refused():
    with pytest.raises(ValueError, match="time zone"):
        FakeClock(datetime(2026, 1, 1, 12, 0))  # noqa: DTZ001
    with pytest.raises(ValueError, match="time zone"):
        FakeClock().set(datetime(2026, 1, 1, 12, 0))  # noqa: DTZ001
