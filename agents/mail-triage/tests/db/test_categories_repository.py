"""U-mail-categories-03, criterion 9 (AC-37, ADR-0043): the repository never returns another mailbox's rows."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import OTHER_ID
from app.db.pg_categories import category_counts, current_list, filed_category
from tests.db.conftest import write_list

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

SHARED_MESSAGE = "m-shared"


@pytest.fixture
async def session(cat_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(cat_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as opened:
        yield opened
    await engine.dispose()


async def _seed_two_mailboxes(owner: asyncpg.Connection, api: asyncpg.Connection) -> dict[str, uuid.UUID]:
    await write_list(api, "mb1", 1, ["Bills"])
    await write_list(api, "mb1", 2, ["Bills", "Travel"])
    await write_list(api, "mb2", 1, ["Work"])
    ids: dict[str, uuid.UUID] = {
        str(r["name"]): r["id"]
        for r in await owner.fetch("select name, id from categories.category where mailbox_id = 'mb1' and version = 2")
    }
    work = uuid.UUID(str(await owner.fetchval("select id from categories.category where mailbox_id = 'mb2'")))
    await owner.execute(
        "insert into categories.category_count (mailbox_id, category_id, mail_count) values "
        f"('mb1', '{ids['Bills']}', 7), ('mb1', '{OTHER_ID}', 3), ('mb2', '{work}', 99), ('mb2', '{OTHER_ID}', 55)"
    )
    await owner.execute(
        "insert into categories.filing (mailbox_id, message_id, list_version, topic_id) values "
        f"('mb1', '{SHARED_MESSAGE}', 2, '{ids['Travel']}'), ('mb2', '{SHARED_MESSAGE}', 1, '{work}')"
    )
    return {**ids, "Work": work}


async def test_given_two_mailboxes_when_the_repository_reads_the_list_then_each_gets_only_its_own_current_version(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, session: AsyncSession
) -> None:
    await _seed_two_mailboxes(cat_owner, cat_api)

    first = await current_list(session, "mb1")
    second = await current_list(session, "mb2")
    empty = await current_list(session, "mb3")

    assert (first.version, [c.name for c in first.categories]) == (2, ["Bills", "Travel"])
    assert (second.version, [c.name for c in second.categories]) == (1, ["Work"])
    assert (empty.version, empty.categories) == (0, ())


async def test_given_two_mailboxes_when_the_repository_reads_counts_and_filings_then_nothing_crosses_over(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, session: AsyncSession
) -> None:
    ids = await _seed_two_mailboxes(cat_owner, cat_api)

    assert await category_counts(session, "mb1") == {ids["Bills"]: 7, OTHER_ID: 3}
    assert await category_counts(session, "mb2") == {ids["Work"]: 99, OTHER_ID: 55}
    assert await category_counts(session, "mb3") == {}
    assert await filed_category(session, "mb1", SHARED_MESSAGE) == ids["Travel"]
    assert await filed_category(session, "mb2", SHARED_MESSAGE) == ids["Work"]
    assert await filed_category(session, "mb3", SHARED_MESSAGE) is None
