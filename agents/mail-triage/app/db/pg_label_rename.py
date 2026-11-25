"""The rename plan in PostgreSQL: the plan items, their hash, the confirmation, the restore request (ADR-0061).

One store per mailbox (ADR-0043); every statement filters on ``mailbox_id``. The agent role may do exactly these
writes (``app/db/grants.sql``): insert, update and delete plan items, set the plan hash of a ``pending`` plan, move a
confirmed plan to ``done`` (a trigger refuses every other state change) and set ``processed_at`` of a restore request.
It cannot write a confirmation or a restore request, and it cannot move ``pending`` to ``confirmed``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import exists, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import LabelConfirmation, LabelMigration, LabelRenameItem, LabelRestoreRequest
from app.db.pg_list_sync import PgListSyncStore
from app.usecases.label_rename import ItemState, StoredItem
from app.usecases.list_sync import MigrationState

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.rename_plan import PlanItem

__all__ = ["PgRenameStore"]


class PgRenameStore:
    """``RenameStore`` on ``categories.label_migration`` and its tables. Each call is its own transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox this store works for."""
        self._sessions = sessions
        self._mailbox = mailbox_id
        self._settings = PgListSyncStore(sessions, mailbox_id)

    async def migration_state(self) -> MigrationState | None:
        """The state of the plan; ``None`` when the mailbox has no row."""
        return await self._settings.migration_state()

    async def items(self) -> list[StoredItem]:
        """Every plan item, by label id."""
        async with self._sessions() as session:
            rows = await session.execute(
                select(LabelRenameItem)
                .where(LabelRenameItem.mailbox_id == self._mailbox)
                .order_by(LabelRenameItem.label_id)
            )
            return [
                StoredItem(
                    row.label_id,
                    row.old_name,
                    row.new_name,
                    row.mail_count,
                    "merge" if row.action == "merge" else "rename",
                    ItemState(row.state),
                )
                for row in rows.scalars()
            ]

    async def write_plan(self, items: Sequence[PlanItem]) -> int:
        """Write the plan and store its hash, only while the state is ``pending`` and no item exists.

        The migration row is locked first, so two overlapping passes write one plan. The hash is computed by the
        database from the stored items. A plan without items moves the state to ``done``.
        """
        async with self._sessions.begin() as session:
            state = (
                await session.execute(
                    select(LabelMigration.state).where(LabelMigration.mailbox_id == self._mailbox).with_for_update()
                )
            ).scalar_one_or_none()
            has_items = (
                await session.execute(select(exists().where(LabelRenameItem.mailbox_id == self._mailbox)))
            ).scalar_one()
            if state != MigrationState.PENDING.value or has_items:
                return 0
            if items:
                await session.execute(
                    insert(LabelRenameItem),
                    [
                        {
                            "mailbox_id": self._mailbox,
                            "label_id": item.label_id,
                            "old_name": item.old_name,
                            "new_name": item.new_name,
                            "mail_count": item.mail_count,
                            "action": item.action,
                        }
                        for item in items
                    ],
                )
                plan_hash = (
                    await session.execute(
                        text("SELECT categories.label_plan_hash(:mailbox)"), {"mailbox": self._mailbox}
                    )
                ).scalar_one()
                values: dict[str, str] = {"plan_hash": plan_hash}
            else:
                values = {"state": MigrationState.DONE.value}
            await session.execute(
                update(LabelMigration).where(LabelMigration.mailbox_id == self._mailbox).values(**values)
            )
            return len(items)

    async def skipped_ids(self) -> frozenset[str] | None:
        """The ids the user skipped in the preview; ``None`` while there is no confirmation."""
        async with self._sessions() as session:
            found = (
                await session.execute(
                    select(LabelConfirmation.skipped_ids).where(LabelConfirmation.mailbox_id == self._mailbox)
                )
            ).scalar_one_or_none()
        return None if found is None else frozenset(found)

    async def settle(self, label_id: str, to: ItemState, *, was: ItemState) -> None:
        """Move one item from ``was`` to ``to``; an item in another state is left as it is."""
        async with self._sessions.begin() as session:
            await session.execute(
                update(LabelRenameItem)
                .where(
                    LabelRenameItem.mailbox_id == self._mailbox,
                    LabelRenameItem.label_id == label_id,
                    LabelRenameItem.state == was.value,
                )
                .values(state=to.value)
            )

    async def complete(self) -> bool:
        """``confirmed`` to ``done`` when no item is planned; True when this call made the change."""
        waiting = exists().where(LabelRenameItem.mailbox_id == self._mailbox, LabelRenameItem.state == "planned")
        async with self._sessions.begin() as session:
            done = await session.execute(
                update(LabelMigration)
                .where(
                    LabelMigration.mailbox_id == self._mailbox,
                    LabelMigration.state == MigrationState.CONFIRMED.value,
                    ~waiting,
                )
                .values(state=MigrationState.DONE.value)
                .returning(LabelMigration.mailbox_id)
            )
            return done.first() is not None

    async def open_restore(self) -> str | None:
        """The id of the open restore request, if any."""
        async with self._sessions() as session:
            found = (
                await session.execute(
                    select(LabelRestoreRequest.id).where(
                        LabelRestoreRequest.mailbox_id == self._mailbox, LabelRestoreRequest.processed_at.is_(None)
                    )
                )
            ).scalar_one_or_none()
        return None if found is None else str(found)

    async def close_restore(self, request_id: str) -> None:
        """Mark the request processed (the one column the agent may set)."""
        async with self._sessions.begin() as session:
            await session.execute(
                update(LabelRestoreRequest)
                .where(
                    LabelRestoreRequest.mailbox_id == self._mailbox,
                    LabelRestoreRequest.id == uuid.UUID(request_id),
                    LabelRestoreRequest.processed_at.is_(None),
                )
                .values(processed_at=func.now())
            )

    async def archive_name(self) -> str:
        """The name of the archive label in the latest list version."""
        return (await self._settings.label_settings()).archive
