"""The database side of the label sync: the rename state, the managed label ids, the derived tables and the cursor.

One store per mailbox (ADR-0043); every statement filters on ``mailbox_id``. The agent role may do exactly these writes
(grants.sql). Nothing is seeded here: the first list comes from the upload (ADR-0060). ``PgLabelBook`` is the
``LabelBook`` of triage and catch-up on the same tables.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.judgement import OTHER_ID as OTHER_CATEGORY
from app.core.managed import Role
from app.db.models import (
    CategoryCount,
    CategoryMailbox,
    GmailLabel,
    LabelMigration,
    ListCursor,
    ListSettings,
    ListVersion,
)
from app.db.models import ManagedLabel as ManagedLabelTable
from app.db.pg_categories import CurrentList, current_list
from app.db.pg_resort import read_managed_labels
from app.usecases.list_sync import LabelKey, LabelSettings, MigrationState, StoredLabel
from category_policy import ARCHIVE_LABEL_DEFAULT, OTHER_LABEL_DEFAULT

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.managed import ManagedLabel, ManagedSet
    from app.usecases.list_sync import ManagedSink
    from app.usecases.resort_apply import ResortLabels

logger = logging.getLogger(__name__)

__all__ = ["NAMES_TTL_SECONDS", "PgLabelBook", "PgListSyncStore"]

NAMES_TTL_SECONDS = 60.0  # how long the Gmail label names of a run are reused: a run is far shorter than the cadence


class PgListSyncStore:
    """``ListSyncStore`` on PostgreSQL. Each call is its own transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox this store works for."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    async def current_list(self) -> CurrentList:
        """The latest list version; version 0 and no categories until the upload."""
        async with self._sessions() as session:
            return await current_list(session, self._mailbox)

    async def cursor(self) -> int:
        """The last version whose Gmail effects are done; 0 before the first."""
        async with self._sessions() as session:
            found = (
                await session.execute(select(ListCursor.last_version).where(ListCursor.mailbox_id == self._mailbox))
            ).scalar_one_or_none()
        return found or 0

    async def migration_state(self) -> MigrationState | None:
        """The state of the rename plan; ``None`` when the mailbox has no row yet."""
        async with self._sessions() as session:
            found = (
                await session.execute(select(LabelMigration.state).where(LabelMigration.mailbox_id == self._mailbox))
            ).scalar_one_or_none()
        return None if found is None else MigrationState(found)

    async def start_migration(self, state: MigrationState) -> MigrationState:
        """Write the first state when there is none; an overlapping run that was first keeps its state."""
        async with self._sessions.begin() as session:
            await session.execute(insert(CategoryMailbox).values(id=self._mailbox).on_conflict_do_nothing())
            await session.execute(
                insert(LabelMigration)
                .values(mailbox_id=self._mailbox, state=state.value)
                .on_conflict_do_nothing(index_elements=["mailbox_id"])
            )
        stored = await self.migration_state()
        return stored if stored is not None else state

    async def label_settings(self) -> LabelSettings:
        """The names of "Other" and the archive label in the latest list version (the defaults before any)."""
        latest = select(func.max(ListVersion.version)).where(ListVersion.mailbox_id == self._mailbox)
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ListSettings.other_label, ListSettings.archive_label).where(
                        ListSettings.mailbox_id == self._mailbox, ListSettings.version == latest.scalar_subquery()
                    )
                )
            ).first()
        if row is None:
            return LabelSettings(OTHER_LABEL_DEFAULT, ARCHIVE_LABEL_DEFAULT)
        return LabelSettings(row.other_label, row.archive_label)

    async def managed_ids(self) -> dict[LabelKey, StoredLabel]:
        """The stored Gmail label of each managed label."""
        async with self._sessions() as session:
            rows = await session.execute(
                select(
                    ManagedLabelTable.role,
                    ManagedLabelTable.category_id,
                    ManagedLabelTable.label_id,
                    ManagedLabelTable.label_name,
                ).where(ManagedLabelTable.mailbox_id == self._mailbox)
            )
            return {_key(row.role, row.category_id): StoredLabel(row.label_id, row.label_name) for row in rows}

    async def save_managed(self, key: LabelKey, label_id: str, label_name: str) -> None:
        """Remember the Gmail label of a managed key; a later call replaces the earlier one, in one transaction."""
        async with self._sessions.begin() as session:
            await session.execute(insert(CategoryMailbox).values(id=self._mailbox).on_conflict_do_nothing())
            await session.execute(
                delete(ManagedLabelTable).where(
                    ManagedLabelTable.mailbox_id == self._mailbox,
                    ManagedLabelTable.role == key.kind,
                    ManagedLabelTable.category_id.is_not_distinct_from(key.category_id),
                )
            )
            statement = insert(ManagedLabelTable).values(
                mailbox_id=self._mailbox,
                label_id=label_id,
                role=key.kind,
                category_id=key.category_id,
                label_name=label_name,
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["mailbox_id", "label_id"],
                    set_={
                        "role": statement.excluded.role,
                        "category_id": statement.excluded.category_id,
                        "label_name": statement.excluded.label_name,
                    },
                )
            )

    async def replace_derived(self, counts: dict[uuid.UUID, int], label_names: list[str]) -> None:
        """Replace the mail counts (by category id, "Other" under the nil id) and the managed label names."""
        async with self._sessions.begin() as session:
            await session.execute(delete(CategoryCount).where(CategoryCount.mailbox_id == self._mailbox))
            await session.execute(delete(GmailLabel).where(GmailLabel.mailbox_id == self._mailbox))
            if counts:
                await session.execute(
                    insert(CategoryCount),
                    [{"mailbox_id": self._mailbox, "category_id": k, "mail_count": v} for k, v in counts.items()],
                )
            if label_names:
                await session.execute(
                    insert(GmailLabel), [{"mailbox_id": self._mailbox, "name": name} for name in label_names]
                )

    async def advance_cursor(self, version: int) -> None:
        """Record that the Gmail effects of ``version`` are done."""
        statement = insert(ListCursor).values(mailbox_id=self._mailbox, last_version=version)
        statement = statement.on_conflict_do_update(
            index_elements=["mailbox_id"], set_={"last_version": statement.excluded.last_version}
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)


def _key(role: str, category_id: uuid.UUID | None) -> LabelKey:
    if role == "category":
        return LabelKey("category", category_id)
    return LabelKey("other") if role == "other" else LabelKey("archive")


class PgLabelBook:
    """The ``LabelBook`` of triage and catch-up on ``managed_label`` and the list settings (ADR-0060).

    Every read goes to the database, so a list saved a moment ago is seen at once; the adapters that guard label
    writes (``followers``) get the managed set each time it is read. The Gmail names are asked from Gmail once per
    ``NAMES_TTL_SECONDS`` and again after a label id was remembered (a label was made).
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        mailbox_id: str,
        label_names: Callable[[], dict[str, str]],
        *,
        followers: Sequence[ManagedSink] = (),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Keep the sessions, the mailbox, the blocking Gmail names call, the guarded adapters and the clock."""
        self._sessions = sessions
        self._mailbox = mailbox_id
        self._label_names = label_names
        self._followers = tuple(followers)
        self._clock = clock
        self._names: dict[str, str] | None = None
        self._names_at = 0.0

    async def _read(self) -> ResortLabels:
        """Read the managed labels and hand them to the guarded adapters."""
        labels = await read_managed_labels(self._sessions, self._mailbox)
        for follower in self._followers:
            follower.set_managed(labels.managed)
        return labels

    async def managed(self) -> ManagedSet:
        """The managed labels of this moment; the guarded adapters get them too."""
        return (await self._read()).managed

    async def names(self) -> dict[str, str]:
        """Gmail label id to its current name; reused for a short time."""
        if self._names is None or self._clock() - self._names_at >= NAMES_TTL_SECONDS:
            self._names = await asyncio.to_thread(self._label_names)
            self._names_at = self._clock()
        return dict(self._names)

    async def other(self) -> ManagedLabel:
        """The "Other" setting: its name and, once known, its Gmail id."""
        return (await self._read()).by_category[OTHER_CATEGORY]

    async def topic(self, category_id: str) -> ManagedLabel:
        """The list label of one category of the current list."""
        return (await self._read()).by_category[category_id]

    async def remember(self, label: ManagedLabel, label_id: str) -> None:
        """Store the Gmail id of a managed label; a label that left the list meanwhile is not stored."""
        found = await self._read()
        key = self._key_of(found.by_category, label)
        if key is None:
            logger.warning("label book: a label to remember is no longer on the list")
            return
        await PgListSyncStore(self._sessions, self._mailbox).save_managed(key, label_id, label.name)
        self._names = None  # a label was made or made again: the names are out of date

    @staticmethod
    def _key_of(by_category: Mapping[str, ManagedLabel], label: ManagedLabel) -> LabelKey | None:
        if label.role is Role.ARCHIVE:
            return LabelKey("archive")
        if label.role is Role.OTHER:
            return LabelKey("other")
        for category_id, candidate in by_category.items():
            if category_id != OTHER_CATEGORY and candidate.name == label.name and candidate.role is label.role:
                return LabelKey("category", uuid.UUID(category_id))
        return None
