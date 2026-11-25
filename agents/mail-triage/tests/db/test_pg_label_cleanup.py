"""U-label-prefix-removal-08 on PostgreSQL: the timer store, the three settings and the time a label left the list."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.label_cleanup import Timer
from app.db.pg_label_cleanup import CleanupSettings, PgLabelCleanupStore, StoredTimer
from tests.db.agent_engine import create_agent_engine
from tests.db.conftest import insert_list, write_list

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    import asyncpg

MAILBOX = "mb1"
T0 = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine whose connections act as the agent role: the grants are part of what is tested."""
    created = create_agent_engine(cat_url)
    yield created
    await created.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgLabelCleanupStore:
    return PgLabelCleanupStore(async_sessionmaker(engine, expire_on_commit=False), MAILBOX)


@pytest.fixture
def other_store(engine: AsyncEngine) -> PgLabelCleanupStore:
    return PgLabelCleanupStore(async_sessionmaker(engine, expire_on_commit=False), "mb2")


async def test_given_no_timer_when_started_then_it_is_stored_with_both_times_equal(store: PgLabelCleanupStore) -> None:
    await store.start_timer("Label_1", T0)

    assert await store.timers() == {"Label_1": StoredTimer(T0, T0)}


async def test_given_a_running_timer_when_started_again_then_the_first_start_stands(store: PgLabelCleanupStore) -> None:
    await store.start_timer("Label_1", T0)
    await store.start_timer("Label_1", T0 + timedelta(hours=1))

    assert await store.timers() == {"Label_1": StoredTimer(T0, T0)}


async def test_given_a_running_timer_when_touched_then_only_the_last_seen_moves_and_never_back(
    store: PgLabelCleanupStore,
) -> None:
    await store.start_timer("Label_1", T0)

    await store.touch("Label_1", T0 + timedelta(minutes=15))
    await store.touch("Label_1", T0 + timedelta(minutes=5))

    assert await store.timers() == {"Label_1": StoredTimer(T0, T0 + timedelta(minutes=15))}


async def test_given_no_timer_when_touched_then_none_is_made(store: PgLabelCleanupStore) -> None:
    await store.touch("Label_1", T0)

    assert await store.timers() == {}


async def test_given_a_timer_when_cleared_then_it_is_gone_and_a_new_start_begins_again(
    store: PgLabelCleanupStore,
) -> None:
    await store.start_timer("Label_1", T0)

    await store.clear("Label_1")
    await store.clear("Label_unknown")
    assert await store.timers() == {}

    later = T0 + timedelta(hours=2)
    await store.start_timer("Label_1", later)
    assert await store.timers() == {"Label_1": StoredTimer(later, later)}


async def test_given_timers_of_two_mailboxes_when_read_and_cleared_then_each_sees_only_its_own(
    store: PgLabelCleanupStore, other_store: PgLabelCleanupStore
) -> None:
    await store.start_timer("Label_1", T0)
    await other_store.start_timer("Label_1", T0 + timedelta(hours=1))

    await other_store.clear("Label_1")

    assert await store.timers() == {"Label_1": StoredTimer(T0, T0)}
    assert await other_store.timers() == {}


def test_given_a_stored_timer_when_joined_with_the_wait_then_it_is_the_timer_of_the_rule() -> None:
    stored = StoredTimer(T0, T0 + timedelta(minutes=15))

    assert stored.with_wait(timedelta(hours=1)) == Timer(T0, T0 + timedelta(minutes=15), timedelta(hours=1))


async def test_given_no_schedule_row_when_the_settings_are_read_then_the_defaults_come_back(
    store: PgLabelCleanupStore,
) -> None:
    assert await store.settings() == CleanupSettings(
        wait=timedelta(minutes=720), protection=timedelta(days=7), retention=timedelta(days=30)
    )


async def test_given_a_schedule_row_when_the_settings_are_read_then_its_three_values_come_back(
    store: PgLabelCleanupStore, cat_owner: asyncpg.Connection
) -> None:
    await cat_owner.execute(
        "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, "
        "updated_by, label_wait_minutes, label_protection_days, label_retention_days) "
        "values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', 'u1', 5, 1, 90)"
    )

    assert await store.settings() == CleanupSettings(
        wait=timedelta(minutes=5), protection=timedelta(days=1), retention=timedelta(days=90)
    )


async def _category_ids(connection: asyncpg.Connection, version: int) -> dict[str, uuid.UUID]:
    rows = await connection.fetch(
        "select name, id from categories.category where mailbox_id = $1 and version = $2", MAILBOX, version
    )
    return {row["name"]: row["id"] for row in rows}


async def _created_at(connection: asyncpg.Connection, version: int) -> datetime:
    found = await connection.fetchval(
        "select created_at from categories.list_version where mailbox_id = $1 and version = $2", MAILBOX, version
    )
    assert isinstance(found, datetime)
    return found


async def _manage(connection: asyncpg.Connection, label_id: str, name: str, category_id: uuid.UUID) -> None:
    await connection.execute(
        "insert into categories.managed_label (mailbox_id, label_id, role, category_id, label_name) "
        "values ($1, $2, 'category', $3, $4)",
        MAILBOX,
        label_id,
        category_id,
        name,
    )


async def test_given_a_category_dropped_in_version_2_when_asked_then_it_left_when_version_2_was_made(
    store: PgLabelCleanupStore, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills", "Travel"])
    ids = await _category_ids(cat_owner, 1)
    async with cat_owner.transaction():
        await insert_list(cat_owner, MAILBOX, 2, [])
        await cat_owner.execute(
            "insert into categories.category (mailbox_id, version, id, name, description, position) "
            "values ($1, 2, $2, 'Bills', 'about', 0)",
            MAILBOX,
            ids["Bills"],
        )
    await _manage(cat_owner, "Label_bills", "Bills", ids["Bills"])
    await _manage(cat_owner, "Label_travel", "Travel", ids["Travel"])

    assert await store.left_list() == {"Label_travel": await _created_at(cat_owner, 2)}


async def test_given_a_category_dropped_in_version_2_and_back_in_3_when_asked_then_it_has_not_left(
    store: PgLabelCleanupStore, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Travel"])
    ids = await _category_ids(cat_owner, 1)
    await write_list(cat_owner, MAILBOX, 2, [])
    async with cat_owner.transaction():
        await cat_owner.execute("insert into categories.list_version (mailbox_id, version) values ($1, 3)", MAILBOX)
        await cat_owner.execute(
            "insert into categories.category (mailbox_id, version, id, name, description, position) "
            "values ($1, 3, $2, 'Travel', 'about', 0)",
            MAILBOX,
            ids["Travel"],
        )
    await _manage(cat_owner, "Label_travel", "Travel", ids["Travel"])

    assert await store.left_list() == {}


async def test_given_a_category_dropped_in_2_and_back_and_dropped_again_in_4_when_asked_then_the_last_leaving_counts(
    store: PgLabelCleanupStore, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Travel"])
    ids = await _category_ids(cat_owner, 1)
    await write_list(cat_owner, MAILBOX, 2, [])
    async with cat_owner.transaction():
        await cat_owner.execute("insert into categories.list_version (mailbox_id, version) values ($1, 3)", MAILBOX)
        await cat_owner.execute(
            "insert into categories.category (mailbox_id, version, id, name, description, position) "
            "values ($1, 3, $2, 'Travel', 'about', 0)",
            MAILBOX,
            ids["Travel"],
        )
    await write_list(cat_owner, MAILBOX, 4, [])
    await _manage(cat_owner, "Label_travel", "Travel", ids["Travel"])

    assert await store.left_list() == {"Label_travel": await _created_at(cat_owner, 4)}


async def test_given_other_and_archive_labels_stored_when_asked_then_they_never_left(
    store: PgLabelCleanupStore, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    await write_list(cat_owner, MAILBOX, 2, [])
    await cat_owner.execute(
        "insert into categories.managed_label (mailbox_id, label_id, role, label_name) "
        "values ($1, 'Label_other', 'other', 'Other'), ($1, 'Label_archive', 'archive', 'Archive')",
        MAILBOX,
    )

    assert await store.left_list() == {}


async def test_given_no_list_at_all_when_asked_then_nothing_has_left(store: PgLabelCleanupStore) -> None:
    assert await store.left_list() == {}
