"""Bounds of the agent settings the user changes in the web app (ADR-0060 point 6, spec D11).

Whole numbers only; the unit is part of each name (minutes, days). Validation reports problems and never raises.
"""

from category_policy.policy import Problem

WAIT_MINUTES_MIN = 5
WAIT_MINUTES_MAX = 12 * 60
WAIT_MINUTES_DEFAULT = 12 * 60
PROTECTION_DAYS_MIN = 1
PROTECTION_DAYS_MAX = 30
PROTECTION_DAYS_DEFAULT = 7
RETENTION_DAYS_MIN = 7
RETENTION_DAYS_MAX = 90
RETENTION_DAYS_DEFAULT = 30

SETTING_BOUND_RULES = (
    "wait_minutes_out_of_range",
    "protection_days_out_of_range",
    "retention_days_out_of_range",
)


def _check(value: int, low: int, high: int, field: str) -> list[Problem]:
    """Refuse anything that is not a whole number from ``low`` to ``high`` (a bool is not a number here)."""
    if isinstance(value, bool) or not low <= value <= high:
        return [Problem(f"{field}_out_of_range", field)]
    return []


def validate_wait_minutes(minutes: int) -> list[Problem]:
    """Check the waiting time before an empty label may be deleted: 5 minutes to 12 hours.

    Args:
        minutes: The waiting time in minutes.

    Returns:
        The problems; empty when valid.
    """
    return _check(minutes, WAIT_MINUTES_MIN, WAIT_MINUTES_MAX, "wait_minutes")


def validate_protection_days(days: int) -> list[Problem]:
    """Check the protection period after a label leaves the list: 1 to 30 days.

    Args:
        days: The protection period in days.

    Returns:
        The problems; empty when valid.
    """
    return _check(days, PROTECTION_DAYS_MIN, PROTECTION_DAYS_MAX, "protection_days")


def validate_retention_days(days: int) -> list[Problem]:
    """Check the retention of the deleted-label record: 7 to 90 days.

    Args:
        days: The retention in days.

    Returns:
        The problems; empty when valid.
    """
    return _check(days, RETENTION_DAYS_MIN, RETENTION_DAYS_MAX, "retention_days")
