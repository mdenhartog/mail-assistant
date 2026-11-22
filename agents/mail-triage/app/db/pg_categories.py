"""Reads of the category list side and the filing write, always for one mailbox (ADR-0043, AC-37).

Every query filters on ``mailbox_id``; the id comes from the caller (the agent's configuration), never from mail
content. The other writes of the agent (seed, counts) arrive with the units that need them.
"""

from __future__ import annotations

import uuid  # noqa: TC003  # used in the runtime annotations of the result types
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Category, CategoryCount, CategorySender, Filing, ListVersion
from category_policy.kinds import Kind
from category_policy.senders import SenderEntry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "CategoryRow",
    "CurrentList",
    "category_counts",
    "current_list",
    "filed_category",
    "record_filing",
]


@dataclass(frozen=True)
class CategoryRow:
    """One category of a list version."""

    id: uuid.UUID
    name: str
    description: str
    position: int
    kind: Kind = Kind.TOPIC
    notify: bool = False
    senders: tuple[SenderEntry, ...] = ()


@dataclass(frozen=True)
class CurrentList:
    """The latest list version of a mailbox; version 0 and no categories until the first version is written."""

    version: int
    categories: tuple[CategoryRow, ...]


async def current_list(session: AsyncSession, mailbox_id: str) -> CurrentList:
    """The latest list version of ``mailbox_id`` with its categories in order."""
    version = (
        await session.execute(
            select(func.coalesce(func.max(ListVersion.version), 0)).where(ListVersion.mailbox_id == mailbox_id)
        )
    ).scalar_one()
    if version == 0:
        return CurrentList(version=0, categories=())
    rows = await session.execute(
        select(Category.id, Category.name, Category.description, Category.position, Category.kind, Category.notify)
        .where(Category.mailbox_id == mailbox_id, Category.version == version)
        .order_by(Category.position)
    )
    senders = await _senders(session, mailbox_id, version)
    return CurrentList(
        version=version,
        categories=tuple(
            CategoryRow(r.id, r.name, r.description, r.position, Kind(r.kind), r.notify, senders.get(r.id, ()))
            for r in rows
        ),
    )


async def _senders(session: AsyncSession, mailbox_id: str, version: int) -> dict[uuid.UUID, tuple[SenderEntry, ...]]:
    """The sender entries of one list version per category, in entry order."""
    rows = await session.execute(
        select(CategorySender.category_id, CategorySender.entry, CategorySender.subdomains)
        .where(CategorySender.mailbox_id == mailbox_id, CategorySender.version == version)
        .order_by(CategorySender.category_id, CategorySender.entry)
    )
    found: dict[uuid.UUID, list[SenderEntry]] = {}
    for row in rows:
        found.setdefault(row.category_id, []).append(SenderEntry(row.entry, row.subdomains))
    return {category_id: tuple(entries) for category_id, entries in found.items()}


async def category_counts(session: AsyncSession, mailbox_id: str) -> dict[uuid.UUID, int]:
    """The mail count per category id (the nil UUID is "Other") of ``mailbox_id``."""
    rows = await session.execute(
        select(CategoryCount.category_id, CategoryCount.mail_count).where(CategoryCount.mailbox_id == mailbox_id)
    )
    return {row.category_id: row.mail_count for row in rows}


async def record_filing(  # noqa: PLR0913, PLR0917 - one column each
    session: AsyncSession,
    mailbox_id: str,
    message_id: str,
    list_version: int,
    topic_id: uuid.UUID,
    extra_id: uuid.UUID | None,
    source: str,
    source_ref: str | None,
) -> None:
    """Write the ``filing`` row of one labelled mail: ids, version, source and the matched entry (AC-39).

    Never sender or subject: ``source_ref`` is the sender entry of the list that matched, nothing of the mail.
    A retry of the same mail under the same list version changes nothing; the time of filing is the database's.
    """
    statement = (
        insert(Filing)
        .values(
            mailbox_id=mailbox_id,
            message_id=message_id,
            list_version=list_version,
            topic_id=topic_id,
            extra_id=extra_id,
            source=source,
            source_ref=source_ref,
        )
        .on_conflict_do_nothing(index_elements=["mailbox_id", "message_id", "list_version"])
    )
    await session.execute(statement)


async def filed_category(session: AsyncSession, mailbox_id: str, message_id: str) -> uuid.UUID | None:
    """The category the newest filing of ``message_id`` put it under, or None when it was never filed."""
    return (
        await session.execute(
            select(Filing.topic_id)
            .where(Filing.mailbox_id == mailbox_id, Filing.message_id == message_id)
            .order_by(Filing.list_version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
