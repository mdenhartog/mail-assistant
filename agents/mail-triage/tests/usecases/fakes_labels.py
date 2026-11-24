"""A fake of the label book that triage and catch-up take their managed labels from (ADR-0060)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.judgement import OTHER_ID
from app.core.managed import ManagedLabel, ManagedSet, Role
from category_policy.kinds import Kind

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.core.judgement import JudgingList


class FakeLabelBook:
    """Managed labels of one list: ids are ``id:<name>`` once known, ``other_name`` is the Other setting."""

    def __init__(  # noqa: PLR0913 - a test fake with every knob
        self,
        current: Callable[[], JudgingList],
        *,
        other_name: str = "Other",
        other_id: str | None = None,
        known_ids: bool = True,
        archive_id: str | None = None,
        names: dict[str, str] | None = None,
    ) -> None:
        self._current = current
        self.other_name = other_name
        self.other_id = other_id
        self.known_ids = known_ids
        self.archive_id = archive_id
        self.label_names = names or {}
        self.remembered: list[tuple[ManagedLabel, str]] = []

    def _id(self, name: str) -> str | None:
        return f"id:{name}" if self.known_ids else None

    def _all(self) -> list[ManagedLabel]:
        labels = [
            ManagedLabel(
                category.name.strip(),
                self._id(category.name.strip()),
                Role.EXTRA if category.kind is Kind.EXTRA else Role.TOPIC,
            )
            for category in self._current().categories
        ]
        if self.archive_id:
            labels.append(ManagedLabel("Archive", self.archive_id, Role.ARCHIVE))
        labels.append(ManagedLabel(self.other_name, self.other_id or self._id(self.other_name), Role.OTHER))
        return labels

    async def managed(self) -> ManagedSet:
        return ManagedSet(self._all())

    async def names(self) -> dict[str, str]:
        return dict(self.label_names)

    async def other(self) -> ManagedLabel:
        return ManagedLabel(self.other_name, self.other_id or self._id(self.other_name), Role.OTHER)

    async def topic(self, category_id: str) -> ManagedLabel:
        assert category_id != OTHER_ID
        for category, label in zip(self._current().categories, self._all(), strict=False):
            if category.category_id == category_id:
                return label
        raise KeyError(category_id)

    async def remember(self, label: ManagedLabel, label_id: str) -> None:
        self.remembered.append((label, label_id))
