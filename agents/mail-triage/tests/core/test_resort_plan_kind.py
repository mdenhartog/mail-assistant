"""U-label-structure-23, criterion 1: which plan an item belongs to (ADR-0056 point 2; "at or above" the threshold)."""

from __future__ import annotations

import pytest

from app.core.resort_plan import PlanKind, kind_for


@pytest.mark.parametrize(
    ("confidence", "threshold", "kind"),
    [
        (95, 80, PlanKind.AUTO),
        (80, 80, PlanKind.AUTO),  # "at or above"
        (79, 80, PlanKind.REVIEW),
        (95, 96, PlanKind.REVIEW),
        (100, 96, PlanKind.AUTO),  # a sender rule is confidence 100
        (99, 100, PlanKind.REVIEW),
        (100, 100, PlanKind.AUTO),
        (0, 50, PlanKind.REVIEW),
    ],
)
def test_given_a_confidence_and_a_threshold_when_routed_then_at_or_above_is_auto(
    confidence: int, threshold: int, kind: PlanKind
) -> None:
    assert kind_for(confidence, threshold) is kind


def test_given_no_threshold_when_routed_then_the_item_waits_for_review() -> None:
    assert kind_for(100, None) is PlanKind.REVIEW
