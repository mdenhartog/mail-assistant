"""U-mail-categories-06, criteria 2, 3 and 6 on PostgreSQL: the store the sync writes through, as the agent role."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.adapters.gmail_resort import GmailResort
from app.db.models import OTHER_ID
from app.db.pg_list_sync import PgListSyncStore
from app.usecases.list_sync import ListSync, StoredLabel
from tests.db.conftest import AGENT_ROLE
from tests.fakes.fake_gmail import FakeGmail

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

MAILBOX = "mb1"


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine whose connections act as the agent role: the grants are part of what is tested."""
    created = create_async_engine(cat_url)

    @event.listens_for(created.sync_engine, "connect")
    def _act_as_agent(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET SESSION AUTHORIZATION "{AGENT_ROLE}"')
        cursor.close()

    yield created
    await created.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgListSyncStore:
    return PgListSyncStore(async_sessionmaker(engine, expire_on_commit=False), MAILBOX)


async def test_given_no_list_when_seeded_then_version_one_has_the_names_in_order_and_the_api_can_read_it(
    store: PgListSyncStore, cat_api: asyncpg.Connection
) -> None:
    current = await store.seed(("Bills", "Travel"))

    assert (current.version, [c.name for c in current.categories]) == (1, ["Bills", "Travel"])
    assert (
        await cat_api.fetchval("select max(version) from categories.list_version where mailbox_id = $1", MAILBOX) == 1
    )
    assert await cat_api.fetchval("select count(*) from categories.category where mailbox_id = $1", MAILBOX) == 2


async def test_given_two_overlapping_first_starts_when_both_seed_then_one_version_one_exists(
    store: PgListSyncStore, cat_owner: asyncpg.Connection
) -> None:
    await asyncio.gather(store.seed(("Bills",)), store.seed(("Bills",)))

    assert await cat_owner.fetchval("select count(*) from categories.list_version") == 1
    assert await cat_owner.fetchval("select count(*) from categories.category") == 1
    assert (await store.current_list()).version == 1


async def test_given_a_list_when_seeded_again_then_nothing_changes(store: PgListSyncStore) -> None:
    await store.seed(("Bills",))

    current = await store.seed(("Other", "Names"))

    assert [c.name for c in current.categories] == ["Bills"]


async def test_given_a_label_when_saved_twice_then_the_latest_name_is_kept(store: PgListSyncStore) -> None:
    category = (await store.seed(("Bills",))).categories[0].id

    await store.save_label(category, "Label_1", "Assistant/Bills")
    await store.save_label(category, "Label_1", "Assistant/Invoices")

    assert await store.stored_labels() == {category: StoredLabel("Label_1", "Assistant/Invoices")}


async def test_given_old_derived_rows_when_replaced_then_only_the_new_ones_remain(
    store: PgListSyncStore, cat_api: asyncpg.Connection
) -> None:
    category = (await store.seed(("Bills",))).categories[0].id
    await store.replace_derived({category: 3, OTHER_ID: 1}, ["Assistant/Bills", "Assistant/Old"])

    await store.replace_derived({category: 4}, ["Assistant/Bills"])

    rows = await cat_api.fetch("select category_id, mail_count from categories.category_count")
    assert {r["category_id"]: r["mail_count"] for r in rows} == {category: 4}
    assert [r["name"] for r in await cat_api.fetch("select name from categories.gmail_label")] == ["Assistant/Bills"]


async def test_given_a_cursor_when_advanced_then_it_reads_back_and_starts_at_zero(store: PgListSyncStore) -> None:
    assert await store.cursor() == 0

    await store.advance_cursor(1)
    await store.advance_cursor(2)

    assert await store.cursor() == 2


async def test_given_a_first_start_when_the_sync_runs_on_postgres_then_the_list_the_labels_and_the_cursor_exist(
    store: PgListSyncStore, cat_api: asyncpg.Connection
) -> None:
    gmail = FakeGmail()
    gmail.add_label("Assistant/Bills")
    gmail.add_mail(labels=(gmail.label_id("Assistant/Bills"),))

    result = await ListSync(GmailResort(gmail, sleep=lambda _s: None), store).run()

    assert (result.version, result.seeded, await store.cursor()) == (1, True, 1)
    assert gmail.label_names().count("Archive") == 1
    names = {r["name"] for r in await cat_api.fetch("select name from categories.gmail_label")}
    assert names == {"Assistant/Bills", "Assistant/Other"}
    assert isinstance(next(iter(await store.stored_labels())), uuid.UUID)


async def test_given_the_test_engine_when_it_connects_then_it_acts_as_the_agent_role(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        assert (await connection.exec_driver_sql("select session_user")).scalar_one() == AGENT_ROLE
