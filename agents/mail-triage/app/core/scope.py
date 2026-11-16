"""Which mail a re-sort plan may touch (spec AC-10, AC-52; ADR-0046).

Pure logic over Gmail label *names*. A mail is in scope when it sits in the inbox or carries one ``Assistant/`` label
and is not spam, trash, archived, a draft or the user's own sent mail. Two ``Assistant/`` labels are unclear: the
mail is counted but never becomes an item, because the agent cannot tell which label is the current one.
"""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "ARCHIVE_LABEL",
    "LABEL_PREFIX",
    "Scope",
    "assistant_labels",
    "classify",
    "clean_display",
    "is_archive_label",
]

LABEL_PREFIX = "Assistant/"
ARCHIVE_LABEL = "Archive"
_INBOX = "INBOX"
_EXCLUDED = frozenset({"SPAM", "TRASH", "DRAFT"})


class Scope(StrEnum):
    """What a plan does with a mail."""

    IN_SCOPE = "in_scope"
    UNCLEAR = "unclear"
    OUT = "out"


def is_archive_label(name: str) -> bool:
    """Whether ``name`` is the top-level ``Archive`` label; case does not matter (C-14), nested names never match."""
    return name.casefold() == ARCHIVE_LABEL.casefold()


def assistant_labels(label_names: Iterable[str]) -> list[str]:
    """The ``Assistant/`` labels among ``label_names`` (exact, case-sensitive prefix), sorted."""
    return sorted(name for name in label_names if name.startswith(LABEL_PREFIX))


def classify(label_names: Iterable[str]) -> Scope:
    """Classify a mail by its label names; excluded labels win over everything else."""
    names = set(label_names)
    if names & _EXCLUDED or any(is_archive_label(name) for name in names):
        return Scope.OUT
    labels = assistant_labels(names)
    if len(labels) > 1:
        return Scope.UNCLEAR
    if labels or _INBOX in names:
        return Scope.IN_SCOPE
    return Scope.OUT


def clean_display(text: str, cap: int) -> str:
    """Text for the review page: format characters (bidi controls, zero-width) removed, other controls to a space.

    The cap counts characters after cleaning (MC-20, AC-44).
    """
    kept = (" " if unicodedata.category(char) == "Cc" else char for char in text if unicodedata.category(char) != "Cf")
    return "".join(kept)[:cap]
