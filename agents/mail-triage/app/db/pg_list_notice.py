"""The list notice in PostgreSQL: button nonces, the list audit, the notice cursor and the restore of a list.

One store per mailbox (ADR-0043); every statement filters on ``mailbox_id``. The agent role may do exactly these writes
(``app/db/grants.sql``): insert a nonce row and set its ``used_at``, read the audit, move the cursor in
``poll_state`` and insert a list version with its categories. The creation time, channel and actor of a restored
version, and its audit record, are derived by the database from the login (ADR-0030), never supplied here.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError

from app.core.list_text import ListCategory
from app.db.models import Category, ListAudit, ListVersion, PollState, TelegramAction
from app.db.pg_update_cursor import POLL_ROW
from app.usecases.list_notice import ListChange, ListChanged
from app.usecases.telegram_actions import ActionRecord

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["PgActionStore", "PgListNoticeStore"]

_CONFLICT: Final = frozenset({"23505", "42501"})  # a second writer took the version (key) or the deferred check refused


class PgActionStore:
    """``ActionStore`` on ``categories.telegram_action``; every call is one short transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    async def insert(self, record: ActionRecord) -> None:
        """Store a new record (the hash only)."""
        statement = insert(TelegramAction).values(
            mailbox_id=self._mailbox,
            nonce_hash=record.nonce_hash,
            chat_id=record.chat_id,
            kind=record.kind,
            target=record.target,
            expires_at=record.expires_at,
        )  # exactly the granted columns, and no RETURNING: the agent cannot read back what the database derives
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def find(self, nonce_hash: str) -> ActionRecord | None:
        """The record with this hash, used or not."""
        statement = select(TelegramAction).where(
            TelegramAction.mailbox_id == self._mailbox, TelegramAction.nonce_hash == nonce_hash
        )
        async with self._sessions() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None
        return ActionRecord(row.nonce_hash, row.chat_id, row.kind, row.target, row.expires_at, row.used_at)

    async def consume(self, nonce_hash: str, chat_id: int, kind: str, now: datetime) -> str | None:
        """The compare-and-set: one statement that matches, marks used and returns the target, or returns nothing."""
        statement = (
            update(TelegramAction)
            .where(
                TelegramAction.mailbox_id == self._mailbox,
                TelegramAction.nonce_hash == nonce_hash,
                TelegramAction.chat_id == chat_id,
                TelegramAction.kind == kind,
                TelegramAction.used_at.is_(None),
                TelegramAction.expires_at > now,
            )
            .values(used_at=now)
            .returning(TelegramAction.target)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).scalar_one_or_none()


def _category(row: Mapping[str, object]) -> ListCategory:
    return ListCategory(str(row["id"]), str(row["name"]), str(row["description"]))


def _change(row: ListAudit) -> ListChange:
    return ListChange(
        row.version,
        row.at,
        row.channel,
        tuple(_category(item) for item in row.old_list),
        tuple(_category(item) for item in row.new_list),
    )


class PgListNoticeStore:
    """``ListNoticeStore`` on the list audit, ``poll_state`` and the list tables."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    async def last_announced(self) -> int:
        """The version up to which changes were announced (0 when none)."""
        async with self._sessions() as session:
            row = await session.get(PollState, POLL_ROW)
        return (row.list_notice_version if row else None) or 0

    async def pending_after(self, version: int) -> list[ListChange]:
        """Audit records above ``version``, lowest version first."""
        statement = (
            select(ListAudit)
            .where(ListAudit.mailbox_id == self._mailbox, ListAudit.version > version)
            .order_by(ListAudit.version)
        )
        async with self._sessions() as session:
            return [_change(row) for row in (await session.execute(statement)).scalars()]

    async def change(self, version: int) -> ListChange | None:
        """The audit record of ``version``."""
        async with self._sessions() as session:
            row = await session.get(ListAudit, (self._mailbox, version))
        return None if row is None else _change(row)

    async def advance(self, version: int) -> None:
        """Move the cursor to ``version`` unless it is already higher; the other columns of the row stay."""
        statement = insert(PollState).values(id=POLL_ROW, list_notice_version=version)
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "list_notice_version": func.greatest(
                    func.coalesce(PollState.list_notice_version, 0), statement.excluded.list_notice_version
                )
            },
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def restore(self, categories: Sequence[ListCategory], expected_version: int) -> int:
        """Write ``categories`` as the next version when the latest is ``expected_version``; else ``ListChanged``.

        The categories keep their ids (the identities exist). Two writers at once cannot both take the next number: the
        key of ``list_version`` and the deferred check of the database let one commit; the other is a changed list.
        """
        try:
            return await self._write(categories, expected_version)
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) in _CONFLICT and await self._latest() != expected_version:
                raise ListChanged from None
            raise

    async def _latest(self) -> int:
        statement = select(func.coalesce(func.max(ListVersion.version), 0)).where(
            ListVersion.mailbox_id == self._mailbox
        )
        async with self._sessions() as session:
            return (await session.execute(statement)).scalar_one()

    async def _write(self, categories: Sequence[ListCategory], expected_version: int) -> int:
        async with self._sessions.begin() as session:
            statement = select(func.coalesce(func.max(ListVersion.version), 0)).where(
                ListVersion.mailbox_id == self._mailbox
            )
            if (await session.execute(statement)).scalar_one() != expected_version:
                raise ListChanged
            version = expected_version + 1
            await session.execute(insert(ListVersion).values(mailbox_id=self._mailbox, version=version))
            for position, category in enumerate(categories):
                await session.execute(
                    insert(Category).values(
                        mailbox_id=self._mailbox,
                        version=version,
                        id=uuid.UUID(category.id),
                        name=category.name,
                        description=category.description,
                        position=position,
                    )
                )
        return version
