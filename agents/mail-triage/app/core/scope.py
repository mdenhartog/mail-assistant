"""Which mail a re-sort plan may touch (spec AC-10, AC-52; ADR-0046, ADR-0060).

Pure logic over Gmail label ids. A mail is in scope when it sits in the inbox or carries a managed label (see
``managed``) and is not spam, trash, in the archive label, a draft or the sent mail of the user. A label that is not
managed, such as a folder the user made, never puts a mail in scope. A topic label (or "Other") next to an extra label
is clear. Two topic labels or two extra labels are unclear: the mail is counted but never becomes an item, because the
agent cannot tell which label is the current one.
"""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import TYPE_CHECKING

from app.core.managed import Role
from category_policy import OTHER_LABEL_DEFAULT, validate_label_setting_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.core.managed import LabelRef, ManagedSet

__all__ = [
    "ArchiveLabel",
    "Scope",
    "classify",
    "clean_display",
    "is_archive_label",
    "usable_archive_name",
]

_INBOX = "INBOX"
_SPACED_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})  # controls, U+2028 and U+2029
_EXCLUDED = frozenset({"SPAM", "TRASH", "DRAFT", "SENT"})


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
    """The name rules of ADR-0060 from the shared policy (without the check against the categories)."""
    return not validate_label_setting_name(name, (), OTHER_LABEL_DEFAULT)


def is_archive_label(name: str, archive: str) -> bool:
    """Whether ``name`` is the configured archive label; case does not matter (C-14, ADR-0052)."""
    return name.casefold() == archive.casefold()


def classify(labels: Iterable[LabelRef], managed: ManagedSet) -> Scope:
    """Classify a mail by its labels; excluded labels and the archive label win over everything else.

    A label counts when ``managed`` finds it by id (by name only while its id is not known). The inbox keeps a mail in
    scope without any managed label.
    """
    refs = list(labels)
    if any(ref.label_id in _EXCLUDED for ref in refs):
        return Scope.OUT
    found = [label for ref in refs if (label := managed.find(ref)) is not None]
    if any(label.role is Role.ARCHIVE for label in found):
        return Scope.OUT
    extras = sum(label.role is Role.EXTRA for label in found)
    if extras > 1 or len(found) - extras > 1:
        return Scope.UNCLEAR
    if found or any(ref.label_id == _INBOX for ref in refs):
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
