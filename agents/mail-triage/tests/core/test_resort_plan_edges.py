"""Edges of the plan time rules that the state tables do not reach (mutation gate, U-mail-categories-34)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, tzinfo

import pytest

from app.core.resort_plan import ListChange, Plan, PlanState, approve, discard_stale, start_apply

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


class _NoOffset(tzinfo):
    """A time zone object that is set but cannot tell its offset."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None


def test_given_a_scheduled_plan_when_now_is_after_apply_after_then_it_starts() -> None:
    plan = Plan(PlanState.SCHEDULED, NOW, NOW)
    assert start_apply(plan, now=NOW + timedelta(hours=1)).state is PlanState.APPLYING
    assert start_apply(plan, now=NOW).state is PlanState.APPLYING


def test_given_a_time_zone_without_an_offset_when_used_then_it_is_refused() -> None:
    odd = datetime(2026, 11, 14, 12, 0, tzinfo=_NoOffset())
    plan = Plan(PlanState.READY, None, NOW)
    with pytest.raises(ValueError, match="timezone"):
        approve(plan, now=odd, delay=timedelta(0))
    with pytest.raises(ValueError, match="timezone"):
        start_apply(Plan(PlanState.SCHEDULED, NOW, NOW), now=odd)
    with pytest.raises(ValueError, match="timezone"):
        discard_stale(plan, now=odd)


def test_given_the_time_rules_when_called_by_position_then_they_are_refused() -> None:
    plan = Plan(PlanState.READY, None, NOW)
    with pytest.raises(TypeError):
        approve(plan, NOW, timedelta(0))  # type: ignore[misc]
    with pytest.raises(TypeError):
        start_apply(plan, NOW)  # type: ignore[misc]
    with pytest.raises(TypeError):
        discard_stale(plan, NOW)  # type: ignore[misc]


def test_given_a_plan_and_a_list_change_when_changed_then_they_are_frozen_and_slotted() -> None:
    for value, field in (
        (Plan(PlanState.READY, None, NOW), "state"),
        (ListChange(PlanState.READY, True, False), "state"),
    ):
        assert not hasattr(value, "__dict__")
        with pytest.raises(FrozenInstanceError):
            value.__setattr__(field, PlanState.APPLIED)
