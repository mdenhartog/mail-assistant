"""The kind of a category (INT-008, C-2)."""

from enum import StrEnum


class Kind(StrEnum):
    """What a category is for.

    A mail has exactly one ``topic`` (or the built-in "Other") and at most one ``extra`` label next to it.
    """

    TOPIC = "topic"
    EXTRA = "extra"
