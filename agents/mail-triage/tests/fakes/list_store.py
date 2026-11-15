"""An in-memory ``ListSyncStore`` for the use-case tests; the PostgreSQL one has its own tests."""

from __future__ import annotations

import uuid

from app.db.pg_categories import CategoryRow, CurrentList
from app.usecases.list_sync import StoredLabel


class FakeListStore:
    """The list, the label map, the derived tables and the cursor of one mailbox, with a crash hook."""

    def __init__(self) -> None:
        self.version = 0
        self.categories: tuple[CategoryRow, ...] = ()
        self.labels: dict[uuid.UUID, StoredLabel] = {}
        self.counts: dict[uuid.UUID, int] = {}
        self.label_names: list[str] = []
        self.cursor_version = 0
        self.crash_before_cursor = False
        self.seeded: list[tuple[str, ...]] = []

    def save_list(self, names: list[str], keep: dict[str, uuid.UUID] | None = None) -> dict[str, uuid.UUID]:
        """The api writes a new version: ``keep`` maps a name to a category id that stays (a rename keeps its id)."""
        ids = {name: (keep or {}).get(name, uuid.uuid4()) for name in names}
        self.version += 1
        self.categories = tuple(CategoryRow(ids[n], n, "about", i) for i, n in enumerate(names))
        return ids

    async def current_list(self) -> CurrentList:
        return CurrentList(self.version, self.categories)

    async def cursor(self) -> int:
        return self.cursor_version

    async def stored_labels(self) -> dict[uuid.UUID, StoredLabel]:
        return dict(self.labels)

    async def seed(self, names: tuple[str, ...]) -> CurrentList:
        if self.version == 0:  # a second writer finds version 1 and writes nothing
            self.seeded.append(names)
            self.save_list(list(names))
        return await self.current_list()

    async def save_label(self, category_id: uuid.UUID, label_id: str, label_name: str) -> None:
        self.labels[category_id] = StoredLabel(label_id, label_name)

    async def replace_derived(self, counts: dict[uuid.UUID, int], label_names: list[str]) -> None:
        self.counts = dict(counts)
        self.label_names = sorted(label_names)

    async def advance_cursor(self, version: int) -> None:
        if self.crash_before_cursor:
            self.crash_before_cursor = False
            raise ConnectionResetError("injected: the process dies before the cursor moves")
        self.cursor_version = version
