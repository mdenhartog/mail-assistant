"""The database side of the delayed label delete: the timers, the settings, the lease and the record of deletes.

One store per mailbox (ADR-0043); every statement filters on ``mailbox_id``. The agent role may write
``label_empty_since`` and ``deleted_label`` and read the rest (grants.sql). Times come from the caller, so the store has
no clock; label ids are never logged (ADR-0060 point 8).

The lease (R9) is a PostgreSQL advisory lock, taken with ``pg_try_advisory_xact_lock`` in a transaction that stays open
for the length of the ``async with``. It never waits, needs no table or cleanup, and is released by the database when
the transaction ends, also when the agent crashes or loses its connection, so a stale lease cannot exist.

``label_empty_since`` holds ``empty_since``, ``last_seen_empty`` and ``wait_minutes``, the waiting time the timer
started with (R3, AC 24): a restart, or a lowered setting, leaves a running timer on its own length.

When a label left the list: a managed label of role ``category`` keeps its row in ``managed_label`` after its category
left the list, and the category id is stable across renames. A label left the list at the creation time of the first
list version after the last version that still held its category; a category that is in the latest version has not
left. "Other" and the archive label are settings and never leave while they are the setting.

A label also leaves management without leaving the list: ``save_managed`` replaces or deletes the managed row of a key
(a category pointed at another label, the Other or archive setting swapped away) and records the label id and the time
in ``managed_label_released``. The latest of the two times counts, and a label that is managed again is not released.
A label that was never managed has no time at all: it is a candidate with no protection (D6, A1).
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import (
    Category,
    CategoryMailbox,
    DeletedLabel,
    LabelEmptySince,
    ListVersion,
    ManagedLabelReleased,
    Plan,
    PlanItem,
    Schedule,
)
from app.db.models import ManagedLabel as ManagedLabelTable
from app.db.pg_list_sync import PgListSyncStore
from app.db.pg_resort import read_managed_labels
from app.usecases.label_cleanup import CleanupSettings, StoredTimer

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.usecases.list_sync import MigrationState
    from app.usecases.resort_apply import ResortLabels

__all__ = ["CleanupSettings", "PgLabelCleanupStore", "StoredTimer"]

DEFAULT_WAIT = timedelta(minutes=720)
DEFAULT_PROTECTION = timedelta(days=7)
DEFAULT_RETENTION = timedelta(days=30)
MIN_WAIT = timedelta(minutes=5)  # the bounds of the waiting time (R8; the database checks them too)
MAX_WAIT = timedelta(minutes=720)
NIL_CATEGORY = uuid.UUID(int=0)  # the built-in "Other" in a plan item


_LEASE_NAMESPACE = 0x4C434C45  # "LCLE": the first key of the advisory lock; the second one is the mailbox


class PgLabelCleanupStore:
    """The timers, the settings and the leaving times of one mailbox. Each call is its own transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox this store works for."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    async def timers(self) -> dict[str, StoredTimer]:
        """Every running timer, by Gmail label id."""
        async with self._sessions() as session:
            rows = await session.execute(
                select(
                    LabelEmptySince.label_id,
                    LabelEmptySince.empty_since,
                    LabelEmptySince.last_seen_empty,
                    LabelEmptySince.wait_minutes,
                ).where(LabelEmptySince.mailbox_id == self._mailbox)
            )
            return {
                row.label_id: StoredTimer(row.empty_since, row.last_seen_empty, timedelta(minutes=row.wait_minutes))
                for row in rows
            }

    async def start_timer(self, label_id: str, now: datetime, wait: timedelta) -> None:
        """Start a timer with the waiting time that applies now; a timer that is already running is not restarted."""
        if not MIN_WAIT <= wait <= MAX_WAIT:
            raise ValueError("wait is outside its bounds")
        async with self._sessions.begin() as session:
            await session.execute(insert(CategoryMailbox).values(id=self._mailbox).on_conflict_do_nothing())
            await session.execute(
                insert(LabelEmptySince)
                .values(
                    mailbox_id=self._mailbox,
                    label_id=label_id,
                    empty_since=now,
                    last_seen_empty=now,
                    wait_minutes=int(wait.total_seconds() // 60),
                )
                .on_conflict_do_nothing(index_elements=["mailbox_id", "label_id"])
            )

    async def touch(self, label_id: str, now: datetime) -> None:
        """Record that the label was seen empty at ``now``; the time never moves back and no timer is made."""
        async with self._sessions.begin() as session:
            await session.execute(
                update(LabelEmptySince)
                .where(LabelEmptySince.mailbox_id == self._mailbox, LabelEmptySince.label_id == label_id)
                .values(last_seen_empty=func.greatest(LabelEmptySince.last_seen_empty, now))
            )

    async def clear(self, label_id: str) -> None:
        """Remove the timer (a reset, or after the delete); a label without a timer is fine."""
        async with self._sessions.begin() as session:
            await session.execute(
                delete(LabelEmptySince).where(
                    LabelEmptySince.mailbox_id == self._mailbox, LabelEmptySince.label_id == label_id
                )
            )

    async def migration_state(self) -> MigrationState | None:
        """The state of the rename plan; ``None`` when the mailbox has none."""
        return await PgListSyncStore(self._sessions, self._mailbox).migration_state()

    async def managed(self) -> ResortLabels:
        """The managed labels now: the current list, "Other" and the archive label."""
        return await read_managed_labels(self._sessions, self._mailbox)

    @contextlib.asynccontextmanager
    async def lease(self) -> AsyncGenerator[bool]:
        """The single-writer lease of this mailbox: ``True`` while held, ``False`` at once when another holds it."""
        async with self._sessions.begin() as session:
            held = (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(:space, hashtext(:mailbox))"),
                    {"space": _LEASE_NAMESPACE, "mailbox": self._mailbox},
                )
            ).scalar_one()
            yield bool(held)

    async def resort_label_ids(self) -> frozenset[str]:
        """The Gmail label ids a re-sort in progress moves mail from or to.

        An open plan (building, ready, scheduled or applying) with an item that is not decided or applied yet: every
        category of the item (the pair before and after, topic and extra) is mapped to its label, the nil category
        to the "Other" label. A label of a category that left the list is found too: its row stays in ``managed_label``.
        """
        mailbox = self._mailbox
        open_items = (
            Plan.mailbox_id == mailbox,
            Plan.state.in_(("building", "ready", "scheduled", "applying")),
            PlanItem.state.in_(("pending", "approved")),
        )
        columns = (
            PlanItem.old_category_id,
            PlanItem.new_category_id,
            PlanItem.old_topic_id,
            PlanItem.old_extra_id,
            PlanItem.new_topic_id,
            PlanItem.new_extra_id,
        )
        found: set[uuid.UUID] = set()
        async with self._sessions() as session:
            for column in columns:
                rows = await session.execute(
                    select(column)
                    .join(Plan, (Plan.mailbox_id == PlanItem.mailbox_id) & (Plan.id == PlanItem.plan_id))
                    .where(*open_items, column.is_not(None))
                    .distinct()
                )
                found.update(found_id for found_id in rows.scalars() if found_id is not None)
            if not found:
                return frozenset()
            labels = await session.execute(
                select(ManagedLabelTable.label_id).where(
                    ManagedLabelTable.mailbox_id == mailbox,
                    or_(
                        ManagedLabelTable.category_id.in_(found),
                        (ManagedLabelTable.role == "other") & (NIL_CATEGORY in found),
                    ),
                )
            )
            return frozenset(labels.scalars())

    async def record_deleted(self, label_id_hash: str, name: str, now: datetime) -> None:
        """Write the deleted label: the hash of its id and its name; a label that is recorded already stays as it is."""
        async with self._sessions.begin() as session:
            await session.execute(insert(CategoryMailbox).values(id=self._mailbox).on_conflict_do_nothing())
            await session.execute(
                insert(DeletedLabel)
                .values(mailbox_id=self._mailbox, label_id_hash=label_id_hash, name=name, deleted_at=now)
                .on_conflict_do_nothing(index_elements=["mailbox_id", "label_id_hash"])
            )

    async def deleted_since(self, since: datetime) -> int:
        """How many labels of this mailbox were deleted after ``since``."""
        async with self._sessions() as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(DeletedLabel)
                    .where(DeletedLabel.mailbox_id == self._mailbox, DeletedLabel.deleted_at > since)
                )
            ).scalar_one()

    async def purge_records(self) -> tuple[int, int]:
        """Remove the deleted-label records and the finished rename items past the retention; both counts.

        The database decides what is old (its clock and ``label_retention_days``); the agent supplies nothing.
        """
        async with self._sessions.begin() as session:
            removed = (await session.execute(text("SELECT categories.purge_label_records()"))).scalar_one()
        return int(removed["deleted_label"]), int(removed["label_rename_item"])

    async def settings(self) -> CleanupSettings:
        """The waiting time, the protection period and the retention; the defaults while there is no schedule row."""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(Schedule.label_wait_minutes, Schedule.label_protection_days, Schedule.label_retention_days)
                )
            ).first()
        if row is None:
            return CleanupSettings(DEFAULT_WAIT, DEFAULT_PROTECTION, DEFAULT_RETENTION)
        return CleanupSettings(
            timedelta(minutes=row.label_wait_minutes),
            timedelta(days=row.label_protection_days),
            timedelta(days=row.label_retention_days),
        )

    async def left_list(self) -> dict[str, datetime]:
        """Gmail label id to the time its category left the list, for every stored label that is not in the list."""
        mailbox = self._mailbox
        last_held = (
            select(Category.id.label("category_id"), func.max(Category.version).label("last_version"))
            .where(Category.mailbox_id == mailbox)
            .group_by(Category.id)
            .subquery()
        )
        async with self._sessions() as session:
            current = (
                await session.execute(select(func.max(ListVersion.version)).where(ListVersion.mailbox_id == mailbox))
            ).scalar_one_or_none()
            released = await self._released(session)
            if current is None:
                return released
            dropped = (
                await session.execute(
                    select(ManagedLabelTable.label_id, last_held.c.last_version)
                    .join(last_held, last_held.c.category_id == ManagedLabelTable.category_id)
                    .where(
                        ManagedLabelTable.mailbox_id == mailbox,
                        ManagedLabelTable.role == "category",
                        last_held.c.last_version < current,
                    )
                )
            ).all()
            versions = (
                await session.execute(
                    select(ListVersion.version, ListVersion.created_at)
                    .where(ListVersion.mailbox_id == mailbox)
                    .order_by(ListVersion.version)
                )
            ).all()
        made = {row.version: row.created_at for row in versions}
        found: dict[str, datetime] = dict(released)
        for row in dropped:
            after = min((version for version in made if version > row.last_version), default=None)
            if after is not None:
                found[row.label_id] = max(made[after], found.get(row.label_id, made[after]))
        return found

    async def _released(self, session: AsyncSession) -> dict[str, datetime]:
        """The latest release time of each label id that is not managed now (a managed label is not released)."""
        mailbox = self._mailbox
        latest = (
            await session.execute(
                select(ManagedLabelReleased.label_id, func.max(ManagedLabelReleased.released_at))
                .where(ManagedLabelReleased.mailbox_id == mailbox)
                .group_by(ManagedLabelReleased.label_id)
            )
        ).all()
        managed = (
            await session.execute(select(ManagedLabelTable.label_id).where(ManagedLabelTable.mailbox_id == mailbox))
        ).scalars()
        held = set(managed)
        return {label_id: at for label_id, at in latest if label_id not in held}
