"""State of one re-sort plan and its items (spec AC-16, AC-19, AC-42, AC-50, AC-57; ADR-0046, design "State machines").

Pure logic: no I/O and no clock. Every moment (``now``) is passed in by the caller. The database owns the real state
(compare-and-set under ``FOR UPDATE``); this module says which moves are allowed, and every other move raises a typed
error. A terminal plan never moves again.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

__all__ = [
    "PLAN_MAX_AGE",
    "DecisionsFrozenError",
    "InvalidTransitionError",
    "ItemEvent",
    "ItemState",
    "ListChange",
    "Plan",
    "PlanEvent",
    "PlanKind",
    "PlanNotDueError",
    "PlanNotExpiredError",
    "PlanState",
    "approve",
    "build_may_start",
    "discard_stale",
    "item_transition",
    "kind_for",
    "may_start_next_batch",
    "on_list_changed",
    "start_apply",
    "transition",
]

PLAN_MAX_AGE = timedelta(days=14)  # AC-19: a plan that is still ready after this long is discarded


class PlanState(StrEnum):
    """Where a plan is in its life."""

    BUILDING = "building"
    READY = "ready"
    SCHEDULED = "scheduled"
    APPLYING = "applying"
    APPLIED = "applied"
    REPLACED = "replaced"
    DISCARDED = "discarded"
    CANCELLED = "cancelled"


class PlanKind(StrEnum):
    """Who approves a plan (ADR-0056): ``auto`` by the agent through the threshold, ``review`` by the user."""

    AUTO = "auto"
    REVIEW = "review"


class ItemState(StrEnum):
    """Where one planned move is."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"


class PlanEvent(StrEnum):
    """What can happen to a plan."""

    BUILD_DONE = "build_done"
    LIST_CHANGED = "list_changed"
    APPROVE = "approve"
    CANCEL = "cancel"
    LOCK = "lock"
    START_APPLY = "start_apply"
    FINISH_APPLY = "finish_apply"
    EXPIRE = "expire"


class ItemEvent(StrEnum):
    """What can happen to an item."""

    APPROVE = "approve"
    REJECT = "reject"
    APPLY = "apply"
    SKIP = "skip"
    FAIL = "fail"


class InvalidTransitionError(ValueError):
    """The event does not fit the state."""


class DecisionsFrozenError(InvalidTransitionError):
    """A decision was attempted on a plan that is already scheduled or later."""


class PlanNotDueError(InvalidTransitionError):
    """The plan is scheduled but ``apply_after`` has not been reached."""


class PlanNotExpiredError(InvalidTransitionError):
    """The ready plan is not older than ``PLAN_MAX_AGE``."""


@dataclass(frozen=True, slots=True)
class Plan:
    """The facts about a plan that the time rules need."""

    state: PlanState
    apply_after: datetime | None
    last_activity_at: datetime  # the last decision, or when the plan became ready


@dataclass(frozen=True, slots=True)
class ListChange:
    """What a list change does to the plan that is in flight."""

    state: PlanState
    discard_decisions: bool
    next_build_waits: bool


_TERMINAL = frozenset({PlanState.APPLIED, PlanState.REPLACED, PlanState.DISCARDED, PlanState.CANCELLED})
_FROZEN = frozenset({PlanState.SCHEDULED, PlanState.APPLYING, PlanState.APPLIED, PlanState.CANCELLED})

_TRANSITIONS: dict[tuple[PlanState, PlanEvent], PlanState] = {
    (PlanState.BUILDING, PlanEvent.BUILD_DONE): PlanState.READY,
    (PlanState.BUILDING, PlanEvent.LIST_CHANGED): PlanState.REPLACED,
    (PlanState.READY, PlanEvent.LIST_CHANGED): PlanState.REPLACED,
    (PlanState.READY, PlanEvent.APPROVE): PlanState.SCHEDULED,
    (PlanState.READY, PlanEvent.EXPIRE): PlanState.DISCARDED,
    (PlanState.SCHEDULED, PlanEvent.CANCEL): PlanState.CANCELLED,
    (PlanState.SCHEDULED, PlanEvent.LOCK): PlanState.CANCELLED,
    (PlanState.SCHEDULED, PlanEvent.START_APPLY): PlanState.APPLYING,
    (PlanState.APPLYING, PlanEvent.CANCEL): PlanState.CANCELLED,
    (PlanState.APPLYING, PlanEvent.LOCK): PlanState.CANCELLED,
    (PlanState.APPLYING, PlanEvent.FINISH_APPLY): PlanState.APPLIED,
}

_ITEM_TRANSITIONS: dict[tuple[PlanState, ItemState, ItemEvent], ItemState] = {
    (PlanState.READY, ItemState.PENDING, ItemEvent.APPROVE): ItemState.APPROVED,
    (PlanState.READY, ItemState.PENDING, ItemEvent.REJECT): ItemState.REJECTED,
    (PlanState.APPLYING, ItemState.APPROVED, ItemEvent.APPLY): ItemState.APPLIED,
    (PlanState.APPLYING, ItemState.APPROVED, ItemEvent.SKIP): ItemState.SKIPPED,
    (PlanState.APPLYING, ItemState.APPROVED, ItemEvent.FAIL): ItemState.FAILED,
}


def _require_aware(moment: datetime) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("the moment needs a timezone")


def _require_state(plan: Plan, expected: PlanState, event: PlanEvent) -> None:
    if plan.state is not expected:
        raise InvalidTransitionError(f"{event} is not allowed while the plan is {plan.state}")


def transition(state: PlanState, event: PlanEvent) -> PlanState:
    """Return the next state, or raise ``InvalidTransitionError`` when the event does not fit.

    Time rules (``apply_after``, the 14 days) live in ``approve``, ``start_apply`` and ``discard_stale``; the effect
    of a list change on a plan in flight lives in ``on_list_changed``.

    Raises:
        InvalidTransitionError: The event is not allowed in this state.
    """
    try:
        return _TRANSITIONS[(state, event)]
    except KeyError:
        raise InvalidTransitionError(f"{event} is not allowed while the plan is {state}") from None


def on_list_changed(state: PlanState) -> ListChange:
    """Decide what a list change does to the plan that is in flight (AC-16, AC-50).

    ``building`` and ``ready`` are replaced and their decisions discarded. ``scheduled`` and ``applying`` finish
    first and the next build waits. A terminal plan is not touched and nothing waits.
    """
    if state in (PlanState.BUILDING, PlanState.READY):
        return ListChange(transition(state, PlanEvent.LIST_CHANGED), discard_decisions=True, next_build_waits=False)
    return ListChange(state, discard_decisions=False, next_build_waits=state not in _TERMINAL)


def kind_for(confidence_pct: int, threshold: int | None) -> PlanKind:
    """The plan an item belongs to: ``auto`` when its confidence is at or above the threshold, else ``review``.

    A sender-rule item is confidence 100, so it is ``auto`` at every threshold. Without a threshold (a plan that has no
    request) nothing is ``auto``.
    """
    if threshold is not None and confidence_pct >= threshold:
        return PlanKind.AUTO
    return PlanKind.REVIEW


def build_may_start(current: PlanState | None) -> bool:
    """A new build starts only when the mailbox has no plan, or its plan is terminal (one non-terminal plan)."""
    return current is None or current in _TERMINAL


def may_start_next_batch(state: PlanState) -> bool:
    """The apply loop checks this before every batch; Cancel and Lock make it false (AC-42, AC-57)."""
    return state is PlanState.APPLYING


def approve(plan: Plan, *, now: datetime, delay: timedelta) -> Plan:
    """Approve a ready plan: ``scheduled``, to be applied from ``now + delay``.

    Raises:
        InvalidTransitionError: The plan is not ready.
        ValueError: ``now`` has no timezone or ``delay`` is negative.
    """
    _require_aware(now)
    if delay < timedelta(0):
        raise ValueError("the delay cannot be negative")
    return Plan(
        state=transition(plan.state, PlanEvent.APPROVE),
        apply_after=now + delay,
        last_activity_at=now,
    )


def start_apply(plan: Plan, *, now: datetime) -> Plan:
    """Start applying a scheduled plan once ``now >= apply_after``.

    Raises:
        InvalidTransitionError: The plan is not scheduled.
        PlanNotDueError: ``apply_after`` is missing or not reached.
        ValueError: ``now`` has no timezone.
    """
    _require_aware(now)
    _require_state(plan, PlanState.SCHEDULED, PlanEvent.START_APPLY)
    if plan.apply_after is None or now < plan.apply_after:
        raise PlanNotDueError("the plan is not due yet")
    return replace(plan, state=transition(plan.state, PlanEvent.START_APPLY))


def discard_stale(plan: Plan, *, now: datetime) -> Plan:
    """Discard a ready plan whose last activity is more than ``PLAN_MAX_AGE`` ago (AC-19).

    Raises:
        InvalidTransitionError: The plan is not ready.
        PlanNotExpiredError: The plan is not older than ``PLAN_MAX_AGE``.
        ValueError: ``now`` has no timezone.
    """
    _require_aware(now)
    _require_state(plan, PlanState.READY, PlanEvent.EXPIRE)
    if now - plan.last_activity_at <= PLAN_MAX_AGE:
        raise PlanNotExpiredError("the plan is not old enough to discard")
    return replace(plan, state=transition(plan.state, PlanEvent.EXPIRE))


def item_transition(plan_state: PlanState, item: ItemState, event: ItemEvent) -> ItemState:
    """Return the next item state: decisions only in a ready plan, outcomes only while the plan is applying.

    Raises:
        DecisionsFrozenError: A decision was attempted on a plan that is scheduled or later.
        InvalidTransitionError: Any other move.
    """
    if event in (ItemEvent.APPROVE, ItemEvent.REJECT) and plan_state in _FROZEN:
        raise DecisionsFrozenError(f"decisions are frozen while the plan is {plan_state}")
    try:
        return _ITEM_TRANSITIONS[(plan_state, item, event)]
    except KeyError:
        raise InvalidTransitionError(
            f"{event} is not allowed on a {item} item while the plan is {plan_state}"
        ) from None
