"""The database side of the label sync: seed version 1, the label map, the derived tables and the list cursor.

One store per mailbox (ADR-0043); every statement filters on ``mailbox_id``. The agent role may do exactly these writes
(grants.sql); the creation time, channel and actor of the seeded version are the database's.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import (
    Category,
    CategoryCount,
    CategoryIdentity,
    CategoryLabel,
    CategoryMailbox,
    GmailLabel,
    ListCursor,
    ListSettings,
    ListVersion,
    Plan,
)
from app.db.pg_categories import CurrentList, current_list
from app.usecases.list_sync import ArchiveNames, StoredLabel
from category_policy import ARCHIVE_LABEL_DEFAULT

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SEED_VERSION = 1


class PgListSyncStore:
    """``ListSyncStore`` on PostgreSQL. Each call is its own transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox this store works for."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    async def current_list(self) -> CurrentList:
        """The latest list version."""
        async with self._sessions() as session:
            return await current_list(session, self._mailbox)

    async def cursor(self) -> int:
        """The last version whose Gmail effects are done; 0 before the first."""
        async with self._sessions() as session:
            found = (
                await session.execute(select(ListCursor.last_version).where(ListCursor.mailbox_id == self._mailbox))
            ).scalar_one_or_none()
        return found or 0

    async def archive_names(self) -> ArchiveNames:
        """The archive label name of the latest list version and of the cursor version (``None``: none done yet).

        A version without a settings row (the agent's own first list) holds the default name.
        """
        async with self._sessions() as session:
            latest = select(func.max(ListVersion.version)).where(ListVersion.mailbox_id == self._mailbox)
            wanted = await self._archive_at(session, latest.scalar_subquery())
            cursor = (
                await session.execute(select(ListCursor.last_version).where(ListCursor.mailbox_id == self._mailbox))
            ).scalar_one_or_none()
            applied = await self._archive_at(session, cursor) if cursor else None
        return ArchiveNames(wanted or ARCHIVE_LABEL_DEFAULT, (applied or ARCHIVE_LABEL_DEFAULT) if cursor else None)

    async def _archive_at(self, session: AsyncSession, version: object) -> str | None:
        return (
            await session.execute(
                select(ListSettings.archive_label).where(
                    ListSettings.mailbox_id == self._mailbox, ListSettings.version == version
                )
            )
        ).scalar_one_or_none()

    async def plan_in_flight(self) -> bool:
        """True while a plan of this mailbox is ``scheduled`` or ``applying``."""
        async with self._sessions() as session:
            found = await session.execute(
                select(Plan.id)
                .where(Plan.mailbox_id == self._mailbox, Plan.state.in_(("scheduled", "applying")))
                .limit(1)
            )
            return found.first() is not None

    async def stored_labels(self) -> dict[uuid.UUID, StoredLabel]:
        """The label of each category by category id."""
        async with self._sessions() as session:
            rows = await session.execute(
                select(CategoryLabel.category_id, CategoryLabel.label_id, CategoryLabel.label_name).where(
                    CategoryLabel.mailbox_id == self._mailbox
                )
            )
            return {row.category_id: StoredLabel(row.label_id, row.label_name) for row in rows}

    async def seed(self, names: tuple[str, ...]) -> CurrentList:
        """Write version 1 with these names when the mailbox has no version; a repeat or overlap writes nothing."""
        async with self._sessions.begin() as session:
            await session.execute(insert(CategoryMailbox).values(id=self._mailbox).on_conflict_do_nothing())
            made = await session.execute(
                insert(ListVersion)
                .values(mailbox_id=self._mailbox, version=SEED_VERSION)
                .on_conflict_do_nothing()
                .returning(ListVersion.version)
            )
            if made.scalar_one_or_none() is not None:
                for position, name in enumerate(names):
                    identity = uuid.uuid4()
                    await session.execute(insert(CategoryIdentity).values(mailbox_id=self._mailbox, id=identity))
                    await session.execute(
                        insert(Category).values(
                            mailbox_id=self._mailbox,
                            version=SEED_VERSION,
                            id=identity,
                            name=name,
                            description="",
                            position=position,
                        )
                    )
        return await self.current_list()

    async def save_label(self, category_id: uuid.UUID, label_id: str, label_name: str) -> None:
        """Remember the Gmail label of a category; a later call replaces the earlier one."""
        statement = insert(CategoryLabel).values(
            mailbox_id=self._mailbox, category_id=category_id, label_id=label_id, label_name=label_name
        )
        statement = statement.on_conflict_do_update(
            index_elements=["mailbox_id", "category_id"],
            set_={"label_id": statement.excluded.label_id, "label_name": statement.excluded.label_name},
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def replace_derived(self, counts: dict[uuid.UUID, int], label_names: list[str]) -> None:
        """Replace the mail counts and the ``Assistant/`` label names in one transaction."""
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
