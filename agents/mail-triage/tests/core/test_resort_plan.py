"""U-mail-categories-13: the re-sort plan state machine (spec AC-16, AC-19, AC-42, AC-50, AC-57; ADR-0046)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import product

import pytest

from app.core.resort_plan import (
    PLAN_MAX_AGE,
    DecisionsFrozenError,
    InvalidTransitionError,
    ItemEvent,
    ItemState,
    Plan,
    PlanEvent,
    PlanNotDueError,
    PlanNotExpiredError,
    PlanState,
    approve,
    build_may_start,
    discard_stale,
    item_transition,
    may_start_next_batch,
    on_list_changed,
    start_apply,
    transition,
)
from tests.fakes.fake_clock import FakeClock

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
DELAY = timedelta(minutes=15)

S = PlanState
E = PlanEvent
TERMINAL = {S.APPLIED, S.REPLACED, S.DISCARDED, S.CANCELLED}

ALLOWED_PLAN: dict[tuple[PlanState, PlanEvent], PlanState] = {
    (S.BUILDING, E.BUILD_DONE): S.READY,
    (S.BUILDING, E.LIST_CHANGED): S.REPLACED,
    (S.READY, E.LIST_CHANGED): S.REPLACED,
    (S.READY, E.APPROVE): S.SCHEDULED,
    (S.READY, E.EXPIRE): S.DISCARDED,
    (S.SCHEDULED, E.CANCEL): S.CANCELLED,
    (S.SCHEDULED, E.LOCK): S.CANCELLED,
    (S.SCHEDULED, E.START_APPLY): S.APPLYING,
    (S.APPLYING, E.CANCEL): S.CANCELLED,
    (S.APPLYING, E.LOCK): S.CANCELLED,
    (S.APPLYING, E.FINISH_APPLY): S.APPLIED,
}


def _plan(state: PlanState, *, apply_after: datetime | None = None, last_activity_at: datetime = NOW) -> Plan:
    return Plan(state=state, apply_after=apply_after, last_activity_at=last_activity_at)


@pytest.mark.parametrize(("state", "event"), list(product(PlanState, PlanEvent)))
def test_given_every_state_and_event_pair_when_transitioned_then_only_the_allowed_ones_succeed(
    state: PlanState, event: PlanEvent
) -> None:
    expected = ALLOWED_PLAN.get((state, event))

    if expected is None:
        with pytest.raises(InvalidTransitionError):
            transition(state, event)
    else:
        assert transition(state, event) is expected


def test_given_a_terminal_plan_when_any_event_arrives_then_it_is_refused() -> None:
    for state, event in product(TERMINAL, PlanEvent):
        with pytest.raises(InvalidTransitionError):
            transition(state, event)


def test_given_the_plan_states_then_they_are_the_eight_of_the_design() -> None:
    assert {s.value for s in PlanState} == {
        "building", "ready", "scheduled", "applying", "applied", "replaced", "discarded", "cancelled",
    }  # fmt: skip
    assert {s.value for s in ItemState} == {"pending", "approved", "rejected", "applied", "skipped", "failed"}


# AC-16
@pytest.mark.parametrize("state", [PlanState.BUILDING, PlanState.READY])
def test_given_a_plan_in_building_or_ready_when_the_list_changes_then_it_is_replaced_and_decisions_are_discarded(
    state: PlanState,
) -> None:
    outcome = on_list_changed(state)

    assert outcome.state is PlanState.REPLACED
    assert outcome.discard_decisions is True
    assert outcome.next_build_waits is False


# AC-50
@pytest.mark.parametrize("state", [PlanState.SCHEDULED, PlanState.APPLYING])
def test_given_a_plan_in_scheduled_or_applying_when_the_list_changes_then_it_finishes_first_and_the_next_build_waits(
    state: PlanState,
) -> None:
    outcome = on_list_changed(state)

    assert outcome.state is state
    assert outcome.discard_decisions is False
    assert outcome.next_build_waits is True


@pytest.mark.parametrize("state", sorted(TERMINAL))
def test_given_a_terminal_plan_when_the_list_changes_then_nothing_changes_and_nothing_waits(state: PlanState) -> None:
    outcome = on_list_changed(state)

    assert outcome.state is state
    assert outcome.discard_decisions is False
    assert outcome.next_build_waits is False


def test_given_the_plan_states_then_a_build_may_start_only_when_there_is_no_non_terminal_plan() -> None:
    assert build_may_start(None) is True
    for state in PlanState:
        assert build_may_start(state) is (state in TERMINAL)


# AC-42, AC-57
@pytest.mark.parametrize("event", [PlanEvent.CANCEL, PlanEvent.LOCK])
def test_given_a_scheduled_plan_when_cancelled_or_locked_then_it_is_cancelled(event: PlanEvent) -> None:
    assert transition(PlanState.SCHEDULED, event) is PlanState.CANCELLED


@pytest.mark.parametrize("event", [PlanEvent.CANCEL, PlanEvent.LOCK])
def test_given_an_applying_plan_when_cancelled_or_locked_then_no_next_batch_may_start(event: PlanEvent) -> None:
    assert may_start_next_batch(PlanState.APPLYING) is True

    after = transition(PlanState.APPLYING, event)

    assert after is PlanState.CANCELLED
    assert may_start_next_batch(after) is False


def test_given_any_state_except_applying_then_no_batch_may_start() -> None:
    for state in PlanState:
        assert may_start_next_batch(state) is (state is PlanState.APPLYING)


# AC-19
def test_given_a_ready_plan_older_than_14_days_when_checked_then_it_is_discarded() -> None:
    plan = _plan(PlanState.READY, last_activity_at=NOW - PLAN_MAX_AGE - timedelta(seconds=1))

    assert discard_stale(plan, now=NOW).state is PlanState.DISCARDED


def test_given_a_ready_plan_of_exactly_14_days_or_less_when_checked_then_it_stays_and_the_check_is_refused() -> None:
    assert timedelta(days=14) == PLAN_MAX_AGE
    for age in (PLAN_MAX_AGE, timedelta(days=1)):
        with pytest.raises(PlanNotExpiredError):
            discard_stale(_plan(PlanState.READY, last_activity_at=NOW - age), now=NOW)


@pytest.mark.parametrize("state", [s for s in PlanState if s is not PlanState.READY])
def test_given_a_plan_that_is_not_ready_when_it_is_old_then_it_is_never_discarded(state: PlanState) -> None:
    old = _plan(state, last_activity_at=NOW - timedelta(days=60))

    with pytest.raises(InvalidTransitionError):
        discard_stale(old, now=NOW)


# approval, apply_after, fake clock
def test_given_a_ready_plan_when_approved_then_it_is_scheduled_with_apply_after() -> None:
    scheduled = approve(_plan(PlanState.READY), now=NOW, delay=DELAY)

    assert scheduled.state is PlanState.SCHEDULED
    assert scheduled.apply_after == NOW + DELAY
    assert scheduled.last_activity_at == NOW


def test_given_a_zero_delay_when_approved_then_apply_after_is_now() -> None:
    assert approve(_plan(PlanState.READY), now=NOW, delay=timedelta(0)).apply_after == NOW


def test_given_a_negative_delay_when_approved_then_it_is_refused() -> None:
    with pytest.raises(ValueError, match="delay"):
        approve(_plan(PlanState.READY), now=NOW, delay=timedelta(minutes=-1))


@pytest.mark.parametrize("state", [s for s in PlanState if s is not PlanState.READY])
def test_given_a_plan_that_is_not_ready_when_approved_then_it_is_refused(state: PlanState) -> None:
    with pytest.raises(InvalidTransitionError):
        approve(_plan(state), now=NOW, delay=DELAY)


def test_given_a_fake_clock_when_apply_after_is_reached_then_and_only_then_the_plan_may_start() -> None:
    clock = FakeClock(NOW)
    scheduled = approve(_plan(PlanState.READY), now=clock.now(), delay=DELAY)

    with pytest.raises(PlanNotDueError):
        start_apply(scheduled, now=clock.now())
    clock.advance(DELAY - timedelta(seconds=1))
    with pytest.raises(PlanNotDueError):
        start_apply(scheduled, now=clock.now())
    clock.advance(timedelta(seconds=1))

    assert start_apply(scheduled, now=clock.now()).state is PlanState.APPLYING


def test_given_a_scheduled_plan_without_apply_after_when_started_then_it_is_refused() -> None:
    with pytest.raises(PlanNotDueError):
        start_apply(_plan(PlanState.SCHEDULED), now=NOW)


@pytest.mark.parametrize("state", [s for s in PlanState if s is not PlanState.SCHEDULED])
def test_given_a_plan_that_is_not_scheduled_when_started_then_it_is_refused_even_when_due(state: PlanState) -> None:
    with pytest.raises(InvalidTransitionError):
        start_apply(_plan(state, apply_after=NOW - timedelta(hours=1)), now=NOW)


def test_given_naive_datetimes_when_used_then_they_are_refused() -> None:
    naive = datetime(2026, 11, 14, 12, 0)  # noqa: DTZ001 - the point of the test
    with pytest.raises(ValueError, match="timezone"):
        approve(_plan(PlanState.READY), now=naive, delay=DELAY)
    with pytest.raises(ValueError, match="timezone"):
        start_apply(_plan(PlanState.SCHEDULED, apply_after=NOW), now=naive)
    with pytest.raises(ValueError, match="timezone"):
        discard_stale(_plan(PlanState.READY), now=naive)


# items
ALLOWED_ITEM: dict[tuple[PlanState, ItemState, ItemEvent], ItemState] = {
    (S.READY, ItemState.PENDING, ItemEvent.APPROVE): ItemState.APPROVED,
    (S.READY, ItemState.PENDING, ItemEvent.REJECT): ItemState.REJECTED,
    (S.APPLYING, ItemState.APPROVED, ItemEvent.APPLY): ItemState.APPLIED,
    (S.APPLYING, ItemState.APPROVED, ItemEvent.SKIP): ItemState.SKIPPED,
    (S.APPLYING, ItemState.APPROVED, ItemEvent.FAIL): ItemState.FAILED,
}


@pytest.mark.parametrize(("plan_state", "item", "event"), list(product(PlanState, ItemState, ItemEvent)))
def test_given_every_plan_item_event_combination_when_transitioned_then_only_the_allowed_ones_succeed(
    plan_state: PlanState, item: ItemState, event: ItemEvent
) -> None:
    expected = ALLOWED_ITEM.get((plan_state, item, event))

    if expected is None:
        with pytest.raises(InvalidTransitionError):
            item_transition(plan_state, item, event)
    else:
        assert item_transition(plan_state, item, event) is expected


@pytest.mark.parametrize(
    "plan_state", [PlanState.SCHEDULED, PlanState.APPLYING, PlanState.APPLIED, PlanState.CANCELLED]
)
@pytest.mark.parametrize("event", [ItemEvent.APPROVE, ItemEvent.REJECT])
def test_given_a_plan_from_scheduled_on_when_a_decision_is_made_then_decisions_are_frozen(
    plan_state: PlanState, event: ItemEvent
) -> None:
    with pytest.raises(DecisionsFrozenError):
        item_transition(plan_state, ItemState.PENDING, event)


@pytest.mark.parametrize("item", [ItemState.APPLIED, ItemState.SKIPPED, ItemState.FAILED, ItemState.REJECTED])
def test_given_a_settled_item_when_any_event_arrives_then_it_is_refused(item: ItemState) -> None:
    for event in ItemEvent:
        with pytest.raises(InvalidTransitionError):
            item_transition(PlanState.APPLYING, item, event)
