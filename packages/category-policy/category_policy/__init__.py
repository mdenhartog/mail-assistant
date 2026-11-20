"""Shared category policy (INT-004): name rules, limits, label mapping and decisions."""

from category_policy.policy import (
    DECISIONS,
    DESCRIPTION_MAX,
    LABEL_PREFIX,
    MAX_CATEGORIES,
    NAME_MAX,
    RULES,
    Category,
    Problem,
    label_for,
    normalise_name,
    validate_category,
    validate_list,
)

__all__ = [
    "DECISIONS",
    "DESCRIPTION_MAX",
    "LABEL_PREFIX",
    "MAX_CATEGORIES",
    "NAME_MAX",
    "RULES",
    "Category",
    "Problem",
    "label_for",
    "normalise_name",
    "validate_category",
    "validate_list",
]
