from datetime import time

from hypothesis import given, settings
from hypothesis import strategies as st

from schedule_policy.parse import parse_time
from schedule_policy.policy import MAX_WINDOW_MINUTES, MIN_WINDOW_MINUTES, validate
from schedule_policy.testing import make_policy

# derandomize=True: the same examples on every run, so a failure is reproducible and CI is not flaky.
FIXED = settings(derandomize=True, max_examples=400, deadline=None)

minutes = st.integers(min_value=0, max_value=24 * 60 - 1)


def _at(total: int) -> time:
    return time(total // 60, total % 60)


@FIXED
@given(start=minutes, end=minutes, overview=minutes, remind=minutes)
def test_given_any_policy_that_passes_validation_when_the_window_is_counted_then_it_is_1_to_12_hours(
    start, end, overview, remind
):
    policy = make_policy(quiet_start=_at(start), quiet_end=_at(end), overview_at=_at(overview), remind_at=_at(remind))
    if validate(policy):
        return

    clock_minutes_inside = sum(policy.is_quiet(_at(m)) for m in range(24 * 60))

    assert MIN_WINDOW_MINUTES <= clock_minutes_inside <= MAX_WINDOW_MINUTES
    assert clock_minutes_inside == policy.window_minutes
    assert not policy.is_quiet(policy.overview_at)
    assert not policy.is_quiet(policy.remind_at)


@FIXED
@given(start=minutes, length=st.integers(min_value=1, max_value=24 * 60 - 1))
def test_given_a_window_of_any_length_when_validated_then_only_60_to_720_minutes_pass(start, length):
    end = (start + length) % (24 * 60)
    # Put overview and reminder at the window end, which is always outside (end exclusive).
    policy = make_policy(quiet_start=_at(start), quiet_end=_at(end), overview_at=_at(end), remind_at=_at(end))

    assert (validate(policy) == []) is (MIN_WINDOW_MINUTES <= length <= MAX_WINDOW_MINUTES)


@FIXED
@given(hour=st.integers(0, 23), minute=st.integers(0, 59))
def test_given_a_formatted_time_when_parsed_then_it_round_trips(hour, minute):
    assert parse_time(f"{hour:02d}:{minute:02d}") == time(hour, minute)
    assert parse_time(f"{hour:02d}{minute:02d}") == time(hour, minute)
    assert parse_time(f"{hour}.{minute:02d}") == time(hour, minute)


@FIXED
@given(text=st.text(max_size=80))
def test_given_any_text_when_parsed_then_it_never_raises_and_gives_a_whole_minute_or_none(text):
    parsed = parse_time(text)

    assert parsed is None or (parsed.second == 0 and parsed.microsecond == 0 and parsed.tzinfo is None)
