"""Which mail a re-sort plan may touch (spec AC-10, AC-52; ADR-0046).

Pure logic over Gmail label *names*. A mail is in scope when it sits in the inbox or carries one ``Assistant/`` label
and is not spam, trash, archived, a draft or the user's own sent mail. Two ``Assistant/`` labels are unclear: the
mail is counted but never becomes an item, because the agent cannot tell which label is the current one.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["ARCHIVE_LABEL", "LABEL_PREFIX", "Scope", "assistant_labels", "classify"]

LABEL_PREFIX = "Assistant/"
ARCHIVE_LABEL = "Archive"
_INBOX = "INBOX"
_EXCLUDED = frozenset({"SPAM", "TRASH", "DRAFT", ARCHIVE_LABEL})


class Scope(StrEnum):
    """What a plan does with a mail."""

    IN_SCOPE = "in_scope"
    UNCLEAR = "unclear"
    OUT = "out"


def assistant_labels(label_names: Iterable[str]) -> list[str]:
    """The ``Assistant/`` labels among ``label_names`` (exact, case-sensitive prefix), sorted."""
    return sorted(name for name in label_names if name.startswith(LABEL_PREFIX))


def classify(label_names: Iterable[str]) -> Scope:
    """Classify a mail by its label names; excluded labels win over everything else."""
    names = set(label_names)
    if names & _EXCLUDED:
        return Scope.OUT
    labels = assistant_labels(names)
    if len(labels) > 1:
        return Scope.UNCLEAR
    if labels or _INBOX in names:
        return Scope.IN_SCOPE
    return Scope.OUT
