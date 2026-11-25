"""The database side of the delayed label delete: the timers, the three settings and when a label left the list.

One store per mailbox (ADR-0043); every statement filters on ``mailbox_id``. The agent role may write
``label_empty_since``
and read the rest (grants.sql). Times come from the caller, so the store has no clock; label ids are never logged
(ADR-0060 point 8).

``label_empty_since`` holds ``empty_since`` and ``last_seen_empty`` only. The wait a timer started with (R3, AC 24) is
NOT stored yet: it needs one more column (``wait_minutes``, additive), see ``StoredTimer.with_wait``.

When a label left the list: a managed label of role ``category`` keeps its row in ``managed_label`` after its category
left the list, and the category id is stable across renames. A label left the list at the creation time of the first
list version after the last version that still held its category; a category that is in the latest version has not
left. "Other" and the archive label are settings and never leave. A label that was never managed (no row) has no leaving
time at all: it is not a candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.label_cleanup import Timer
from app.db.models import Category, CategoryMailbox, LabelEmptySince, ListVersion, Schedule
from app.db.models import ManagedLabel as ManagedLabelTable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["CleanupSettings", "PgLabelCleanupStore", "StoredTimer"]

DEFAULT_WAIT = timedelta(minutes=720)
DEFAULT_PROTECTION = timedelta(days=7)
DEFAULT_RETENTION = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class StoredTimer:
    """A row of ``label_empty_since``: when the label was first seen empty and when last."""

    empty_since: datetime
    last_seen_empty: datetime

    def with_wait(self, wait: timedelta) -> Timer:
        """The timer of the rule, given the wait it started with (to be stored with the row by unit 09)."""
        return Timer(self.empty_since, self.last_seen_empty, wait)


@dataclass(frozen=True, slots=True)
class CleanupSettings:
    """The three agent settings of the cleanup."""

    wait: timedelta
    protection: timedelta
    retention: timedelta


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
                select(LabelEmptySince.label_id, LabelEmptySince.empty_since, LabelEmptySince.last_seen_empty).where(
                    LabelEmptySince.mailbox_id == self._mailbox
                )
            )
            return {row.label_id: StoredTimer(row.empty_since, row.last_seen_empty) for row in rows}

    async def start_timer(self, label_id: str, now: datetime) -> None:
        """Start a timer; a timer that is already running is not restarted."""
        async with self._sessions.begin() as session:
            await session.execute(insert(CategoryMailbox).values(id=self._mailbox).on_conflict_do_nothing())
            await session.execute(
                insert(LabelEmptySince)
                .values(mailbox_id=self._mailbox, label_id=label_id, empty_since=now, last_seen_empty=now)
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
            if current is None:
                return {}
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
        found: dict[str, datetime] = {}
        for row in dropped:
            after = min((version for version in made if version > row.last_version), default=None)
            if after is not None:
                found[row.label_id] = made[after]
        return found
