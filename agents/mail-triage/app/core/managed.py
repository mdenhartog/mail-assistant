"""The managed labels: the only Gmail labels the agent may add, remove, create or rename (ADR-0060).

Pure logic. A label is managed when its Gmail label id is the id of a category of the current list, of "Other" or of
the archive label. A managed label whose id is not known yet is matched by name (any letter case) until the id is
stored; once an id is known, only the id counts, so a hand-renamed label is still found and another label that
carries the old name is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["LabelRef", "ManagedLabel", "ManagedSet", "Role"]


class Role(StrEnum):
    """What a managed label is for."""

    TOPIC = "topic"
    EXTRA = "extra"
    OTHER = "other"
    ARCHIVE = "archive"


@dataclass(frozen=True, slots=True)
class LabelRef:
    """A label as Gmail shows it on a mail: its id and its current name."""

    label_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ManagedLabel:
    """One managed label: the name it should have, the Gmail id once known, and its role."""

    name: str
    label_id: str | None
    role: Role


class ManagedSet:
    """The managed labels of one moment; find a mail's label in it by id, by name only while no id is known."""

    __slots__ = ("_by_id", "_by_name", "archive")

    def __init__(self, labels: Iterable[ManagedLabel]) -> None:
        """Index the labels; ``archive`` is the one with the ``ARCHIVE`` role, ``None`` when there is none."""
        kept = list(labels)
        self._by_id = {label.label_id: label for label in kept if label.label_id is not None}
        self._by_name = {label.name.casefold(): label for label in kept if label.label_id is None}
        self.archive = next((label for label in kept if label.role is Role.ARCHIVE), None)

    def find(self, ref: LabelRef) -> ManagedLabel | None:
        """The managed label ``ref`` is, or ``None`` when it is not managed."""
        return self._by_id.get(ref.label_id) or self._by_name.get(ref.name.casefold())

    def labels(self) -> tuple[ManagedLabel, ...]:
        """Every managed label of the set, with or without a stored id."""
        return (*self._by_id.values(), *self._by_name.values())
