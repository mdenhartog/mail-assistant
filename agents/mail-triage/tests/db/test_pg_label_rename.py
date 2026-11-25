"""U-label-prefix-removal-06 on PostgreSQL: the rename store as the agent role (ADR-0061; guards of migration 0030)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.rename_plan import PlanItem
from app.db.pg_label_rename import PgRenameStore
from app.usecases.label_rename import ItemState
from app.usecases.list_sync import MigrationState
from tests.db.agent_engine import create_agent_engine

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

MAILBOX = "mb1"
PLAN = [
    PlanItem("L1", "Old/Bills", "Bills", "rename", 4),
    PlanItem("L2", "Old/Amerika", "Amerika", "merge", 2),
]


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    created = create_agent_engine(cat_url)
    yield created
    await created.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgRenameStore:
    return PgRenameStore(async_sessionmaker(engine, expire_on_commit=False), MAILBOX)


async def start(owner: asyncpg.Connection, state: str = "pending") -> None:
    await owner.execute("insert into categories.label_migration (mailbox_id, state) values ($1, $2)", MAILBOX, state)


async def test_given_no_state_row_when_read_then_there_is_no_state(store: PgRenameStore) -> None:
    assert await store.migration_state() is None


async def test_given_a_pending_state_when_the_plan_is_written_then_items_and_the_hash_are_stored_once(
    store: PgRenameStore, cat_owner: asyncpg.Connection
) -> None:
    await start(cat_owner)

    assert await store.write_plan(PLAN) == 2
    assert await store.write_plan([PlanItem("L3", "Old/X", "X", "rename")]) == 0  # built once

    stored = {item.label_id: item for item in await store.items()}
    assert set(stored) == {"L1", "L2"}
    assert (stored["L1"].mail_count, stored["L2"].action, stored["L1"].state) == (4, "merge", ItemState.PLANNED)
    expected = await cat_owner.fetchval("select categories.label_plan_hash($1)", MAILBOX)
    assert await cat_owner.fetchval("select plan_hash from categories.label_migration") == expected
    assert await store.migration_state() is MigrationState.PENDING


async def test_given_an_empty_plan_when_written_then_the_state_is_done(
    store: PgRenameStore, cat_owner: asyncpg.Connection
) -> None:
    await start(cat_owner)

    assert await store.write_plan([]) == 0

    assert await store.migration_state() is MigrationState.DONE


async def test_given_a_state_that_is_not_pending_when_a_plan_is_written_then_nothing_is_written(
    store: PgRenameStore, cat_owner: asyncpg.Connection
) -> None:
    await start(cat_owner, "done")

    assert await store.write_plan(PLAN) == 0
    assert await store.items() == []


async def test_given_no_confirmation_then_no_skips_and_after_the_api_confirms_the_skips_are_read(
    store: PgRenameStore, cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await start(cat_owner)
    await store.write_plan(PLAN)
    assert await store.skipped_ids() is None
    plan_hash = await cat_owner.fetchval("select plan_hash from categories.label_migration")

    await cat_api.execute("select categories.confirm_label_rename($1, $2, $3::text[])", MAILBOX, plan_hash, ["L2"])

    assert await store.skipped_ids() == frozenset({"L2"})
    assert await store.migration_state() is MigrationState.CONFIRMED


async def test_given_a_confirmed_plan_when_items_settle_then_done_comes_only_when_none_is_planned(
    store: PgRenameStore, cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await start(cat_owner)
    await store.write_plan(PLAN)
    plan_hash = await cat_owner.fetchval("select plan_hash from categories.label_migration")
    await cat_api.execute("select categories.confirm_label_rename($1, $2, $3::text[])", MAILBOX, plan_hash, [])

    await store.settle("L1", ItemState.DONE, was=ItemState.PLANNED)
    assert await store.complete() is False  # L2 still waits
    await store.settle("L1", ItemState.KEPT, was=ItemState.PLANNED)  # not planned any more: left alone
    await store.settle("L2", ItemState.KEPT, was=ItemState.PLANNED)
    assert await store.complete() is True
    assert await store.complete() is False  # a second call changes nothing

    states = {item.label_id: item.state for item in await store.items()}
    assert states == {"L1": ItemState.DONE, "L2": ItemState.KEPT}
    assert await store.migration_state() is MigrationState.DONE


async def test_given_a_restore_request_when_closed_then_it_is_no_longer_open(
    store: PgRenameStore, cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await start(cat_owner, "done")
    assert await store.open_restore() is None
    await cat_api.execute("select categories.request_label_restore($1)", MAILBOX)

    request = await store.open_restore()
    assert request is not None
    await store.close_restore(request)

    assert await store.open_restore() is None
    assert await cat_owner.fetchval("select processed_at is not null from categories.label_restore_request")


async def test_given_no_settings_row_when_the_archive_name_is_read_then_it_is_the_default(store: PgRenameStore) -> None:
    assert await store.archive_name() == "Archive"


async def test_given_stored_other_archive_and_category_labels_when_asked_then_only_other_and_archive_ids_are_protected(
    store: PgRenameStore, cat_owner: asyncpg.Connection
) -> None:
    await cat_owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)
    await cat_owner.execute(
        "insert into categories.managed_label (mailbox_id, label_id, role, label_name) "
        "values ($1, 'L_O', 'other', 'Other'), ($1, 'L_A', 'archive', 'Archive')",
        MAILBOX,
    )

    assert await store.protected_ids() == frozenset({"L_O", "L_A"})
