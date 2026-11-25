"""U-label-prefix-removal-08: the pure delete rule of the delayed label cleanup (ADR-0060 point 5, R1 to R3, R6, R9)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.core.label_cleanup import Action, LabelFacts, Rules, Timer, decide

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
WAIT = timedelta(hours=12)
PROTECTION = timedelta(days=7)
CYCLE = timedelta(minutes=15)
LEFT = NOW - timedelta(days=30)

EMPTY = LabelFacts(
    label_type="user",
    in_list=False,
    has_child=False,
    messages_total=0,
    threads_total=0,
    filter_target=False,
    left_list_at=LEFT,
)


def ripe(wait: timedelta = WAIT) -> Timer:
    """A timer that started a wait ago and was seen empty at the previous check."""
    return Timer(empty_since=NOW - wait - CYCLE, last_seen_empty=NOW - CYCLE, wait=wait)


def run(facts: LabelFacts, timer: Timer | None, *, wait: timedelta = WAIT) -> Action:
    return decide(facts, timer, now=NOW, rules=Rules(wait, PROTECTION, CYCLE)).action


def test_given_empty_for_the_whole_wait_and_no_blocker_when_decided_then_delete() -> None:
    assert run(EMPTY, ripe()) is Action.DELETE


def test_given_a_label_never_seen_empty_when_decided_then_the_timer_starts_with_the_current_wait() -> None:
    decision = decide(EMPTY, None, now=NOW, rules=Rules(WAIT, PROTECTION, CYCLE))

    assert decision.action is Action.START_TIMER
    assert decision.wait == WAIT


def test_given_an_empty_label_before_the_wait_has_passed_when_decided_then_wait() -> None:
    young = Timer(empty_since=NOW - WAIT + timedelta(minutes=1), last_seen_empty=NOW - CYCLE, wait=WAIT)

    assert run(EMPTY, young) is Action.WAIT


def test_given_a_mail_within_the_wait_when_decided_then_the_timer_resets() -> None:
    running = Timer(empty_since=NOW - timedelta(hours=2), last_seen_empty=NOW - CYCLE, wait=WAIT)

    assert run(replace(EMPTY, messages_total=1, threads_total=1), running) is Action.RESET_TIMER
    assert run(replace(EMPTY, threads_total=1), running) is Action.RESET_TIMER


def test_given_a_mail_and_no_timer_when_decided_then_keep() -> None:
    assert run(replace(EMPTY, messages_total=2), None) is Action.KEEP


def test_given_a_timer_and_a_restart_after_three_hours_when_decided_then_the_timer_is_kept() -> None:
    # The agent was away for 3 hours; with a cycle of one hour that is exactly 3 cycles, which keeps the timer.
    timer = Timer(empty_since=NOW - timedelta(hours=3), last_seen_empty=NOW - timedelta(hours=3), wait=WAIT)
    decision = decide(EMPTY, timer, now=NOW, rules=Rules(WAIT, PROTECTION, timedelta(hours=1)))

    assert decision.action is Action.WAIT


def test_given_a_gap_of_more_than_three_cycles_when_decided_then_the_timer_resets() -> None:
    timer = Timer(
        empty_since=NOW - WAIT - timedelta(hours=1),
        last_seen_empty=NOW - 3 * CYCLE - timedelta(seconds=1),
        wait=WAIT,
    )

    assert run(EMPTY, timer) is Action.RESET_TIMER


def test_given_a_gap_of_exactly_three_cycles_when_decided_then_the_timer_is_kept() -> None:
    timer = Timer(empty_since=NOW - WAIT - timedelta(hours=1), last_seen_empty=NOW - 3 * CYCLE, wait=WAIT)

    assert run(EMPTY, timer) is Action.DELETE


def test_given_a_clock_that_went_back_when_decided_then_the_timer_resets() -> None:
    timer = Timer(empty_since=NOW - WAIT, last_seen_empty=NOW + timedelta(minutes=1), wait=WAIT)

    assert run(EMPTY, timer) is Action.RESET_TIMER


def test_given_a_lowered_wait_when_decided_then_a_running_timer_keeps_its_own_length() -> None:
    running = Timer(empty_since=NOW - timedelta(hours=1), last_seen_empty=NOW - CYCLE, wait=WAIT)

    assert run(EMPTY, running, wait=timedelta(minutes=5)) is Action.WAIT
    assert run(EMPTY, ripe(), wait=timedelta(hours=24)) is Action.DELETE  # and a raised wait does not lengthen it


def test_given_a_timer_that_started_with_a_short_wait_when_the_wait_is_raised_then_the_short_one_counts() -> None:
    short = Timer(empty_since=NOW - timedelta(minutes=30), last_seen_empty=NOW - CYCLE, wait=timedelta(minutes=5))

    assert run(EMPTY, short, wait=WAIT) is Action.DELETE


def test_given_a_label_that_left_the_list_less_than_the_protection_period_ago_when_decided_then_keep() -> None:
    three_days = replace(EMPTY, left_list_at=NOW - timedelta(days=3))

    assert run(three_days, ripe()) is Action.KEEP
    assert run(three_days, None) is Action.KEEP


def test_given_a_label_that_left_exactly_the_protection_period_ago_when_decided_then_it_may_go() -> None:
    assert run(replace(EMPTY, left_list_at=NOW - PROTECTION), ripe()) is Action.DELETE


def test_given_a_label_that_never_was_in_the_list_when_decided_then_nothing_protects_it_and_the_timer_rules() -> None:
    never = replace(EMPTY, left_list_at=None)  # a hand-made empty label, the root "Assistant" (D6)

    assert run(never, None) is Action.START_TIMER
    assert run(never, ripe()) is Action.DELETE
    assert run(never, Timer(NOW - timedelta(hours=1), NOW - CYCLE, WAIT)) is Action.WAIT


def test_given_a_label_that_never_was_in_the_list_when_it_has_another_blocker_then_keep() -> None:
    for blocked in (
        replace(EMPTY, left_list_at=None, label_type="system"),
        replace(EMPTY, left_list_at=None, in_list=True),
        replace(EMPTY, left_list_at=None, filter_target=True),
        replace(EMPTY, left_list_at=None, has_child=True),
        replace(EMPTY, left_list_at=None, messages_total=1),
    ):
        assert run(blocked, ripe()) is not Action.DELETE


def test_given_a_leaving_time_in_the_future_when_decided_then_keep() -> None:
    assert run(replace(EMPTY, left_list_at=NOW + timedelta(hours=1)), ripe()) is Action.KEEP


def test_given_an_empty_parent_and_child_when_decided_then_the_child_goes_first_and_the_parent_later() -> None:
    parent = replace(EMPTY, has_child=True)

    assert run(EMPTY, ripe()) is Action.DELETE  # the child
    assert run(parent, ripe()) is Action.KEEP  # the parent while the child exists, whatever its timer says
    assert run(EMPTY, None) is Action.START_TIMER  # the next cycle, the child is gone: the parent's own timer starts
    assert run(EMPTY, Timer(NOW - timedelta(hours=1), NOW - CYCLE, WAIT)) is Action.WAIT


def test_given_a_blocker_when_decided_then_keep_even_with_a_ripe_timer() -> None:
    for blocked in (
        replace(EMPTY, label_type="system"),
        replace(EMPTY, in_list=True),
        replace(EMPTY, filter_target=True),
        replace(EMPTY, has_child=True),
    ):
        assert run(blocked, ripe()) is Action.KEEP
        assert run(blocked, None) is Action.KEEP


facts = st.builds(
    LabelFacts,
    label_type=st.sampled_from(["user", "system", "", "USER"]),
    in_list=st.booleans(),
    has_child=st.booleans(),
    messages_total=st.integers(min_value=0, max_value=3),
    threads_total=st.integers(min_value=0, max_value=3),
    filter_target=st.booleans(),
    left_list_at=st.none() | st.integers(min_value=-40, max_value=40).map(lambda d: NOW - timedelta(days=d)),
)
timers = st.none() | st.builds(
    Timer,
    empty_since=st.integers(min_value=0, max_value=100_000).map(lambda m: NOW - timedelta(minutes=m)),
    last_seen_empty=st.integers(min_value=-60, max_value=100_000).map(lambda m: NOW - timedelta(minutes=m)),
    wait=st.integers(min_value=5, max_value=720).map(lambda m: timedelta(minutes=m)),
)


@given(facts, timers, st.integers(min_value=5, max_value=720).map(lambda m: timedelta(minutes=m)))
def test_property_a_blocker_never_yields_delete(item: LabelFacts, timer: Timer | None, wait: timedelta) -> None:
    decision = decide(item, timer, now=NOW, rules=Rules(wait, PROTECTION, CYCLE))
    blocked = (
        item.messages_total > 0
        or item.threads_total > 0
        or item.label_type != "user"
        or item.in_list
        or item.filter_target
        or item.has_child
        or (item.left_list_at is not None and NOW - item.left_list_at < PROTECTION)
    )
    if blocked:
        assert decision.action is not Action.DELETE
    if decision.action is Action.DELETE:
        assert timer is not None
        assert NOW - timer.empty_since >= timer.wait
