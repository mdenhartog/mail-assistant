"""Bounds of the agent settings: waiting time, protection period and retention (AC 33, 34; ADR-0060 point 6)."""

import pytest

from category_policy import (
    PROTECTION_DAYS_DEFAULT,
    PROTECTION_DAYS_MAX,
    PROTECTION_DAYS_MIN,
    RETENTION_DAYS_DEFAULT,
    RETENTION_DAYS_MAX,
    RETENTION_DAYS_MIN,
    WAIT_MINUTES_DEFAULT,
    WAIT_MINUTES_MAX,
    WAIT_MINUTES_MIN,
    Problem,
    validate_protection_days,
    validate_retention_days,
    validate_wait_minutes,
)


def test_given_the_bounds_when_read_then_they_are_the_decided_ones():
    assert (WAIT_MINUTES_MIN, WAIT_MINUTES_MAX, WAIT_MINUTES_DEFAULT) == (5, 12 * 60, 12 * 60)
    assert (PROTECTION_DAYS_MIN, PROTECTION_DAYS_MAX, PROTECTION_DAYS_DEFAULT) == (1, 30, 7)
    assert (RETENTION_DAYS_MIN, RETENTION_DAYS_MAX, RETENTION_DAYS_DEFAULT) == (7, 90, 30)


@pytest.mark.parametrize(
    ("check", "field", "rule", "refused", "accepted"),
    [
        (validate_wait_minutes, "wait_minutes", "wait_minutes_out_of_range", (4, 12 * 60 + 1, 0, -1), (5, 6, 720)),
        (validate_protection_days, "protection_days", "protection_days_out_of_range", (0, 31, -1), (1, 7, 30)),
        (validate_retention_days, "retention_days", "retention_days_out_of_range", (6, 91, 0), (7, 30, 90)),
    ],
)
def test_given_values_around_the_bounds_when_validated_then_outside_is_refused_and_the_bounds_are_accepted(
    check, field, rule, refused, accepted
):
    for value in refused:
        assert check(value) == [Problem(rule, field)], value
    for value in accepted:
        assert check(value) == [], value


def test_given_a_bool_when_validated_then_it_is_refused_as_not_a_number():
    assert validate_protection_days(True) == [Problem("protection_days_out_of_range", "protection_days")]
