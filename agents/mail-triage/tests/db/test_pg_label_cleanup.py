"""U-label-prefix-removal-08 on PostgreSQL: the timer store, the three settings and the time a label left the list."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.label_cleanup import Timer
from app.db.pg_label_cleanup import CleanupSettings, PgLabelCleanupStore, StoredTimer
from tests.db.agent_engine import create_agent_engine
from tests.db.conftest import insert_list, write_list
from tests.db.plan_support import seed_plan

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

MAILBOX = "mb1"
T0 = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)
WAIT = timedelta(minutes=45)


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine whose connections act as the agent role: the grants are part of what is tested."""
    created = create_agent_engine(cat_url, pool_size=4)  # the lease holds one connection while the store uses others
    yield created
    await created.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgLabelCleanupStore:
    return PgLabelCleanupStore(async_sessionmaker(engine, expire_on_commit=False), MAILBOX)


@pytest.fixture
def other_store(engine: AsyncEngine) -> PgLabelCleanupStore:
    return PgLabelCleanupStore(async_sessionmaker(engine, expire_on_commit=False), "mb2")


async def test_given_no_timer_when_started_then_it_is_stored_with_both_times_equal(store: PgLabelCleanupStore) -> None:
    await store.start_timer("Label_1", T0, WAIT)

    assert await store.timers() == {"Label_1": StoredTimer(T0, T0, WAIT)}


async def test_given_a_running_timer_when_started_again_then_the_first_start_stands(store: PgLabelCleanupStore) -> None:
    await store.start_timer("Label_1", T0, WAIT)
    await store.start_timer("Label_1", T0 + timedelta(hours=1), WAIT)

    assert await store.timers() == {"Label_1": StoredTimer(T0, T0, WAIT)}


async def test_given_a_running_timer_when_touched_then_only_the_last_seen_moves_and_never_back(
    store: PgLabelCleanupStore,
) -> None:
    await store.start_timer("Label_1", T0, WAIT)

    await store.touch("Label_1", T0 + timedelta(minutes=15))
    await store.touch("Label_1", T0 + timedelta(minutes=5))

    assert await store.timers() == {"Label_1": StoredTimer(T0, T0 + timedelta(minutes=15), WAIT)}


async def test_given_no_timer_when_touched_then_none_is_made(store: PgLabelCleanupStore) -> None:
    await store.touch("Label_1", T0)

    assert await store.timers() == {}


async def test_given_a_timer_when_cleared_then_it_is_gone_and_a_new_start_begins_again(
    store: PgLabelCleanupStore,
) -> None:
    await store.start_timer("Label_1", T0, WAIT)

    await store.clear("Label_1")
    await store.clear("Label_unknown")
    assert await store.timers() == {}

    later = T0 + timedelta(hours=2)
    await store.start_timer("Label_1", later, WAIT)
    assert await store.timers() == {"Label_1": StoredTimer(later, later, WAIT)}


async def test_given_timers_of_two_mailboxes_when_read_and_cleared_then_each_sees_only_its_own(
    store: PgLabelCleanupStore, other_store: PgLabelCleanupStore
) -> None:
    await store.start_timer("Label_1", T0, WAIT)
    await other_store.start_timer("Label_1", T0 + timedelta(hours=1), WAIT)

    await other_store.clear("Label_1")

    assert await store.timers() == {"Label_1": StoredTimer(T0, T0, WAIT)}
    assert await other_store.timers() == {}


def test_given_a_stored_timer_when_read_as_the_rule_then_it_carries_the_wait_it_started_with() -> None:
    stored = StoredTimer(T0, T0 + timedelta(minutes=15), timedelta(hours=1))

    assert stored.timer == Timer(T0, T0 + timedelta(minutes=15), timedelta(hours=1))


async def test_given_a_timer_started_with_45_minutes_when_the_agent_restarts_then_it_keeps_the_45_minutes(
    store: PgLabelCleanupStore, engine: AsyncEngine, cat_owner: asyncpg.Connection
) -> None:
    await store.start_timer("Label_1", T0, WAIT)
    await cat_owner.execute(
        "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, "
        "updated_by, label_wait_minutes) values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', 'u1', 5)"
    )  # the user lowered the waiting time to 5 minutes

    restarted = PgLabelCleanupStore(async_sessionmaker(engine, expire_on_commit=False), MAILBOX)

    assert (await restarted.settings()).wait == timedelta(minutes=5)
    assert (await restarted.timers())["Label_1"].wait == WAIT


async def test_given_a_wait_outside_5_to_720_minutes_when_a_timer_starts_then_it_is_refused(
    store: PgLabelCleanupStore,
) -> None:
    for bad in (timedelta(minutes=4), timedelta(minutes=721)):
        with pytest.raises(ValueError, match="wait"):
            await store.start_timer("Label_1", T0, bad)


async def test_given_records_past_the_retention_when_purged_then_only_those_go_and_the_counts_come_back(
    store: PgLabelCleanupStore, cat_owner: asyncpg.Connection
) -> None:
    await cat_owner.execute(
        "insert into categories.deleted_label (mailbox_id, label_id_hash, name, deleted_at) values "
        "('mb1', $1, 'x', now() - interval '31 days'), ('mb1', $2, 'y', now() - interval '1 day')",
        "a" * 64,
        "b" * 64,
    )

    assert await store.purge_records() == (1, 0)
    assert await cat_owner.fetchval("select count(*) from categories.deleted_label") == 1


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


# --- unit 09: the lease, the label ids a re-sort targets, the record of deleted labels ------------------------------


async def test_given_a_held_lease_when_a_second_caller_asks_then_it_gets_false_at_once_and_true_after_the_release(
    store: PgLabelCleanupStore, engine: AsyncEngine
) -> None:
    second = PgLabelCleanupStore(async_sessionmaker(engine, expire_on_commit=False), MAILBOX)

    async with store.lease() as first:
        assert first is True
        async with second.lease() as held_twice:
            assert held_twice is False

    async with second.lease() as after:
        assert after is True


async def test_given_a_held_lease_when_the_other_mailbox_asks_then_it_has_its_own(
    store: PgLabelCleanupStore, other_store: PgLabelCleanupStore
) -> None:
    async with store.lease() as first, other_store.lease() as other:
        assert (first, other) == (True, True)


async def test_given_a_lease_when_the_holder_fails_then_the_lease_is_free_again(
    store: PgLabelCleanupStore, other_store: PgLabelCleanupStore, engine: AsyncEngine
) -> None:
    again = PgLabelCleanupStore(async_sessionmaker(engine, expire_on_commit=False), MAILBOX)

    with pytest.raises(RuntimeError, match="boom"):
        async with store.lease():
            raise RuntimeError("boom")

    async with again.lease() as held:
        assert held is True


async def test_given_a_deleted_label_when_recorded_then_the_name_and_hash_are_stored_once_and_counted_by_time(
    store: PgLabelCleanupStore, cat_owner: asyncpg.Connection
) -> None:
    digest = "a" * 64

    await store.record_deleted(digest, "Old name", T0)
    await store.record_deleted(digest, "Other name", T0 + timedelta(hours=1))  # the same label again: no second row

    rows = await cat_owner.fetch("select label_id_hash, name, deleted_at from categories.deleted_label")
    assert [(r["label_id_hash"], r["name"], r["deleted_at"]) for r in rows] == [(digest, "Old name", T0)]
    assert await store.deleted_since(T0 - timedelta(seconds=1)) == 1
    assert await store.deleted_since(T0) == 0


async def test_given_open_plans_when_asked_then_only_the_labels_of_open_items_of_open_plans_come_back(
    store: PgLabelCleanupStore, cat_owner: asyncpg.Connection
) -> None:
    ids = {
        name: uuid.UUID(int=n) for n, name in enumerate(("nil", "dropped", "moved_to", "old_done", "applied_plan"), 0)
    }
    for name in ("dropped", "moved_to", "old_done", "applied_plan"):
        await cat_owner.execute(
            "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", MAILBOX, ids[name]
        )
        await cat_owner.execute(
            "insert into categories.managed_label (mailbox_id, label_id, role, category_id, label_name) "
            "values ($1, $2, 'category', $3, $4)",
            MAILBOX,
            f"L_{name}",
            ids[name],
            name,
        )
    await cat_owner.execute(
        "insert into categories.managed_label (mailbox_id, label_id, role, label_name) "
        "values ($1, 'L_other', 'other', 'Other')",
        MAILBOX,
    )
    open_plan = await seed_plan(
        cat_owner,
        MAILBOX,
        state="ready",
        moves=((ids["dropped"], ids["moved_to"]), (ids["old_done"], ids["old_done"]), (ids["nil"], ids["moved_to"])),
        tag="a",
    )
    await cat_owner.execute(
        "update categories.plan_item set state = 'applied', decision = 'approved' "
        "where mailbox_id = $1 and plan_id = $2 and message_id = 'a1'",
        MAILBOX,
        open_plan.plan_id,
    )
    await seed_plan(cat_owner, MAILBOX, state="applied", moves=((ids["applied_plan"], ids["applied_plan"]),), tag="b")

    assert await store.resort_label_ids() == frozenset({"L_dropped", "L_moved_to", "L_other"})
