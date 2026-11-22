"""Which mail a re-sort plan may touch (spec AC-10, AC-52; ADR-0046).

Pure logic over Gmail label *names*. A mail is in scope when it sits in the inbox or carries one ``Assistant/`` label
and is not spam, trash, in the archive label, a draft or the user's own sent mail. Two ``Assistant/`` labels are
unclear: the mail is counted but never becomes an item, because the agent cannot tell which label is the current one.
"""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import TYPE_CHECKING

from category_policy import ARCHIVE_LABEL_DEFAULT

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "LABEL_PREFIX",
    "ArchiveLabel",
    "Scope",
    "assistant_labels",
    "classify",
    "clean_display",
    "is_archive_label",
    "usable_archive_name",
]

LABEL_PREFIX = "Assistant/"
_INBOX = "INBOX"
_SPACED_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})  # controls, U+2028 and U+2029
_EXCLUDED = frozenset({"SPAM", "TRASH", "DRAFT"})
_ARCHIVE_NAME_MAX = 225  # the length Gmail allows for a label name
_SYSTEM_LABELS = frozenset(
    {"inbox", "spam", "trash", "draft", "sent", "starred", "unread", "important", "chat", "snoozed", "scheduled"}
)


class Scope(StrEnum):
    """What a plan does with a mail."""

    IN_SCOPE = "in_scope"
    UNCLEAR = "unclear"
    OUT = "out"


class ArchiveLabel:
    """The protected archive label as the agent knows it now (ADR-0059): the name it has in Gmail and its id.

    One object is shared by every component, so a rename done by the label sync is seen by the plan build, the apply
    and the move back at once. The name stays the old one until Gmail has the new one.
    """

    __slots__ = ("label_id", "name")

    def __init__(self, name: str, label_id: str | None = None) -> None:
        """Start with the name the database holds; the sync fills the id."""
        self.name = name
        self.label_id = label_id


def usable_archive_name(name: str) -> bool:
    """The rules of ADR-0059 point 2: outside ``Assistant/`` or exactly ``Assistant/Archive``; never a system label."""
    key = name.casefold()
    return (
        0 < len(name) <= _ARCHIVE_NAME_MAX
        and name == name.strip()
        and ".." not in name
        and all(name.split("/"))  # no empty part: no leading, trailing or double slash
        and not any(unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in name)
        and key not in _SYSTEM_LABELS
        and not key.startswith("category_")
        and (not key.startswith("assistant/") or name == ARCHIVE_LABEL_DEFAULT)
    )


def is_archive_label(name: str, archive: str) -> bool:
    """Whether ``name`` is the configured archive label; case does not matter (C-14, ADR-0052)."""
    return name.casefold() == archive.casefold()


def assistant_labels(label_names: Iterable[str]) -> list[str]:
    """The ``Assistant/`` labels among ``label_names`` (exact, case-sensitive prefix), sorted."""
    return sorted(name for name in label_names if name.startswith(LABEL_PREFIX))


def classify(label_names: Iterable[str], archive: str) -> Scope:
    """Classify a mail by its label names; excluded labels and the ``archive`` label win over everything else."""
    names = set(label_names)
    if names & _EXCLUDED or any(is_archive_label(name, archive) for name in names):
        return Scope.OUT
    labels = assistant_labels(names)
    if len(labels) > 1:
        return Scope.UNCLEAR
    if labels or _INBOX in names:
        return Scope.IN_SCOPE
    return Scope.OUT


def clean_display(text: str, cap: int) -> str:
    """Text for the review page: format characters (bidi controls, zero-width) removed.

    Controls and the line and paragraph separators become a space.

    The cap counts characters after cleaning (MC-20, AC-44).
    """
    kept = (
        " " if unicodedata.category(char) in _SPACED_CATEGORIES else char
        for char in text
        if unicodedata.category(char) != "Cf"
    )
    return "".join(kept)[:cap]
