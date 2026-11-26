"""An in-memory ``CleanupStore`` for the use-case tests; the PostgreSQL one has its own tests.

It keeps the rules the database keeps: ``start_timer`` does not restart a running timer, ``touch`` never moves back
and makes no timer, the lease is one holder at a time and never waits (``try`` semantics of an advisory lock).
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import TYPE_CHECKING

from app.core.managed import ManagedLabel, ManagedSet, Role
from app.db.pg_label_cleanup import CleanupSettings, StoredTimer
from app.usecases.list_sync import MigrationState
from app.usecases.resort_apply import ResortLabels

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from datetime import datetime


class FakeCleanupStore:
    """The state, the settings, the timers, the managed labels and the record of deleted labels of one mailbox."""

    def __init__(self, state: MigrationState | None = MigrationState.DONE) -> None:
        self.state = state
        self.cleanup_settings = CleanupSettings(timedelta(hours=12), timedelta(days=7), timedelta(days=30))
        self.timer_rows: dict[str, StoredTimer] = {}
        self.managed_labels = ResortLabels(ManagedSet(()), {})
        self.left: dict[str, datetime] = {}
        self.resort_ids: frozenset[str] = frozenset()
        self.deleted: dict[str, tuple[str, datetime]] = {}  # label id hash -> (name, when)
        self.leased = False
        self.lease_refused = False  # another process holds the lease
        self.purges = 0
        self.purged_counts: tuple[int, int] = (0, 0)

    def manage(self, *labels: tuple[str, str | None, Role]) -> None:
        """Make labels (name, id, role) managed: part of the current list or one of the two settings."""
        self.managed_labels = ResortLabels(
            ManagedSet(ManagedLabel(name, label_id, role) for name, label_id, role in labels), {}
        )

    async def migration_state(self) -> MigrationState | None:
        return self.state

    async def settings(self) -> CleanupSettings:
        return self.cleanup_settings

    async def managed(self) -> ResortLabels:
        return self.managed_labels

    async def left_list(self) -> dict[str, datetime]:
        return dict(self.left)

    async def resort_label_ids(self) -> frozenset[str]:
        return self.resort_ids

    async def timers(self) -> dict[str, StoredTimer]:
        return dict(self.timer_rows)

    async def start_timer(self, label_id: str, now: datetime, wait: timedelta) -> None:
        self.timer_rows.setdefault(label_id, StoredTimer(now, now, wait))

    async def touch(self, label_id: str, now: datetime) -> None:
        row = self.timer_rows.get(label_id)
        if row is not None:
            self.timer_rows[label_id] = StoredTimer(row.empty_since, max(row.last_seen_empty, now), row.wait)

    async def clear(self, label_id: str) -> None:
        self.timer_rows.pop(label_id, None)

    @contextlib.asynccontextmanager
    async def lease(self) -> AsyncGenerator[bool]:
        """One holder at a time; a second caller does not wait and gets ``False``."""
        if self.leased or self.lease_refused:
            yield False
            return
        self.leased = True
        try:
            yield True
        finally:
            self.leased = False

    async def record_deleted(self, label_id_hash: str, name: str, now: datetime) -> None:
        self.deleted.setdefault(label_id_hash, (name, now))

    async def deleted_since(self, since: datetime) -> int:
        return sum(1 for _name, when in self.deleted.values() if when > since)

    async def purge_records(self) -> tuple[int, int]:
        self.purges += 1
        return self.purged_counts
