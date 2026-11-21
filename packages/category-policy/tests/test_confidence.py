"""Direct tests for the one confidence scale (AC-5, ADR-0053 decision 4)."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from category_policy import at_or_above, confidence_pct


@pytest.mark.parametrize(("confidence", "pct"), [(0.495, 50), (0.5, 50), (0.795, 80), (0.8, 80)])
def test_given_the_boundary_confidences_when_converted_then_the_percentage_rounds_half_up(confidence: float, pct: int):
    assert confidence_pct(confidence) == pct


def test_given_the_boundary_confidences_when_compared_with_50_and_80_then_the_rounded_value_decides():
    assert at_or_above(confidence_pct(0.495), 50)
    assert at_or_above(confidence_pct(0.795), 80)
    assert not at_or_above(confidence_pct(0.494), 50)
    assert not at_or_above(confidence_pct(0.794), 80)


def test_given_a_percentage_equal_to_the_threshold_when_compared_then_it_is_at_or_above():
    assert at_or_above(80, 80)
    assert at_or_above(81, 80)
    assert not at_or_above(79, 80)


@pytest.mark.parametrize("confidence", [-0.001, 1.001, math.nan, math.inf, -math.inf])
def test_given_a_confidence_outside_zero_to_one_when_converted_then_it_is_refused(confidence: float):
    with pytest.raises(ValueError, match="confidence"):
        confidence_pct(confidence)


@given(st.floats(min_value=0.0, max_value=1.0))
def test_given_any_confidence_when_converted_then_the_percentage_is_within_one_half_of_it(confidence: float):
    pct = confidence_pct(confidence)

    assert 0 <= pct <= 100
    assert abs(pct - confidence * 100) <= 0.5 + 1e-9


@given(st.floats(min_value=0.0, max_value=1.0), st.floats(min_value=0.0, max_value=1.0))
def test_given_two_confidences_when_converted_then_the_order_is_kept(first: float, second: float):
    low, high = sorted((first, second))

    assert confidence_pct(low) <= confidence_pct(high)
