"""An in-memory ``RenameStore`` for the use-case tests; the PostgreSQL one has its own tests.

It keeps the rules the database keeps: a plan is written once and only while the state is ``pending``; only the
confirmation moves ``pending`` to ``confirmed``; ``done`` needs every item settled; ``skipped_ids`` is ``None`` until
there is a confirmation. ``crash_after_settles`` kills the run after that many settled items (a crash of the agent).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from app.usecases.label_rename import ItemState, StoredItem
from app.usecases.list_sync import MigrationState

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from app.core.rename_plan import PlanItem


class FakeRenameStore:
    """The migration state, the plan items, the confirmation and the restore request of one mailbox."""

    def __init__(self, state: MigrationState | None = MigrationState.PENDING, archive: str = "Archive") -> None:
        self.state = state
        self.archive = archive
        self.stored: dict[str, StoredItem] = {}
        self.confirmation: frozenset[str] | None = None
        self.restore_open: str | None = None
        self.restores_closed = 0
        self.plans_written = 0
        self.settles = 0
        self.crash_after_settles: int | None = None

    # --- what the api does -------------------------------------------------------------------------------------

    def confirm(self, skipped: Iterable[str] = ()) -> None:
        """``confirm_label_rename``: the confirmation row and ``pending`` to ``confirmed``."""
        assert self.state is MigrationState.PENDING
        self.confirmation = frozenset(skipped)
        self.state = MigrationState.CONFIRMED

    def request_restore(self) -> None:
        """``request_label_restore``: one open request, only for a confirmed or done plan."""
        assert self.state in (MigrationState.CONFIRMED, MigrationState.DONE)
        self.restore_open = self.restore_open or "request-1"

    def states(self) -> dict[str, ItemState]:
        return {label_id: item.state for label_id, item in self.stored.items()}

    # --- the port ----------------------------------------------------------------------------------------------

    async def migration_state(self) -> MigrationState | None:
        return self.state

    async def items(self) -> list[StoredItem]:
        return list(self.stored.values())

    async def write_plan(self, items: Sequence[PlanItem]) -> int:
        if self.state is not MigrationState.PENDING or self.stored:
            return 0
        self.plans_written += 1
        for item in items:
            self.stored[item.label_id] = StoredItem(
                item.label_id, item.old_name, item.new_name, item.mail_count, item.action, ItemState.PLANNED
            )
        if not items:
            self.state = MigrationState.DONE
        return len(items)

    async def skipped_ids(self) -> frozenset[str] | None:
        return self.confirmation

    async def settle(self, label_id: str, to: ItemState, *, was: ItemState) -> None:
        if self.crash_after_settles is not None and self.settles >= self.crash_after_settles:
            self.crash_after_settles = None
            raise ConnectionResetError("injected: the process dies before the item is settled")
        item = self.stored[label_id]
        if item.state is was:
            self.stored[label_id] = dataclasses.replace(item, state=to)
            self.settles += 1

    async def complete(self) -> bool:
        waiting = any(item.state is ItemState.PLANNED for item in self.stored.values())
        if self.state is MigrationState.CONFIRMED and not waiting:
            self.state = MigrationState.DONE
            return True
        return False

    async def open_restore(self) -> str | None:
        return self.restore_open

    async def close_restore(self, request_id: str) -> None:
        if self.restore_open == request_id:
            self.restore_open = None
            self.restores_closed += 1

    async def archive_name(self) -> str:
        return self.archive
