"""An in-memory ``ListSyncStore`` for the use-case tests; the PostgreSQL one has its own tests."""

from __future__ import annotations

import uuid

from app.db.pg_categories import CategoryRow, CurrentList
from app.usecases.list_sync import LabelKey, LabelSettings, MigrationState, StoredLabel


class FakeListStore:
    """The list, the managed label map, the derived tables and the cursor of one mailbox, with a crash hook."""

    def __init__(self, *, migration: MigrationState | None = None) -> None:
        self.version = 0
        self.categories: tuple[CategoryRow, ...] = ()
        self.managed: dict[LabelKey, StoredLabel] = {}
        self.counts: dict[uuid.UUID, int] = {}
        self.label_names: list[str] = []
        self.cursor_version = 0
        self.crash_before_cursor = False
        self.settings = LabelSettings(other="Other", archive="Archive")  # the names of the latest list version
        self.migration = migration  # ``None``: the mailbox has no row yet
        self.migration_starts: list[MigrationState] = []

    def save_list(self, names: list[str], keep: dict[str, uuid.UUID] | None = None) -> dict[str, uuid.UUID]:
        """The api writes a new version: ``keep`` maps a name to a category id that stays (a rename keeps its id)."""
        ids = {name: (keep or {}).get(name, uuid.uuid4()) for name in names}
        self.version += 1
        self.categories = tuple(CategoryRow(ids[n], n, "about", i) for i, n in enumerate(names))
        return ids

    def stored(self, category_id: uuid.UUID) -> StoredLabel | None:
        return self.managed.get(LabelKey("category", category_id))

    async def current_list(self) -> CurrentList:
        return CurrentList(self.version, self.categories)

    async def cursor(self) -> int:
        return self.cursor_version

    async def migration_state(self) -> MigrationState | None:
        return self.migration

    async def start_migration(self, state: MigrationState) -> MigrationState:
        if self.migration is None:  # a second writer finds the row and writes nothing
            self.migration = state
            self.migration_starts.append(state)
        return self.migration

    async def label_settings(self) -> LabelSettings:
        return self.settings

    async def managed_ids(self) -> dict[LabelKey, StoredLabel]:
        return dict(self.managed)

    async def save_managed(self, key: LabelKey, label_id: str, label_name: str) -> None:
        self.managed[key] = StoredLabel(label_id, label_name)

    async def replace_derived(self, counts: dict[uuid.UUID, int], label_names: list[str]) -> None:
        self.counts = dict(counts)
        self.label_names = sorted(label_names)

    async def advance_cursor(self, version: int) -> None:
        if self.crash_before_cursor:
            self.crash_before_cursor = False
            raise ConnectionResetError("injected: the process dies before the cursor moves")
        self.cursor_version = version
