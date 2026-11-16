"""U-mail-categories-32: the plan keeps how many mails an apply moved, after the moved items are gone (AC-39, C-18).

``remove_applied_items`` deletes the items the apply moved at once, so the count cannot be read from the items later.
Migration 0022 adds ``plan.moved_count``; the definer function adds the number it removes, in the same statement
sequence. The agent has no right to write the column itself, so it cannot forge the number. The api may read it, and
the apply settings, which the review page shows.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import asyncpg
from alembic import command

from app.core.resort_plan import ItemState
from app.db.pg_resort import PgApplyStore
from app.usecases.resort_apply import SkipReason
from tests.db.conftest import AGENT_ROLE, API_ROLE, alembic_config, plain_url
from tests.db.resort_support import MAILBOX, agent_sessions
from tests.db.test_pg_resort_apply import scheduled_plan

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]  # the fixture is used by name


async def _applied_plan(owner: asyncpg.Connection, store: PgApplyStore) -> Any:
    plan_id = await scheduled_plan(owner, moves=4)
    await store.finish_item(plan_id, "m0", ItemState.APPLIED, None)
    await store.finish_item(plan_id, "m1", ItemState.APPLIED, None)
    await store.finish_item(plan_id, "m2", ItemState.SKIPPED, SkipReason.GONE)
    await store.finish_item(plan_id, "m3", ItemState.FAILED, None)
    await owner.execute("update categories.plan set state = 'applying'")
    await owner.execute("update categories.plan set state = 'applied'")
    return plan_id


async def test_given_a_new_plan_when_read_then_the_moved_count_is_zero(cat_owner: asyncpg.Connection) -> None:
    await scheduled_plan(cat_owner, moves=1)

    assert await cat_owner.fetchval("select moved_count from categories.plan") == 0


async def test_given_an_applied_plan_when_the_moved_items_are_removed_then_their_number_stays_on_the_plan(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _applied_plan(cat_owner, store)

    await store.remove_applied_items(plan_id)

    assert await cat_owner.fetchval("select count(*) from categories.plan_item where state = 'applied'") == 0
    assert await cat_owner.fetchval("select moved_count from categories.plan where id = $1", plan_id) == 2


async def test_given_the_removal_runs_again_when_nothing_is_left_then_the_count_is_not_lost(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _applied_plan(cat_owner, store)

    await store.remove_applied_items(plan_id)
    await store.remove_applied_items(plan_id)

    assert await cat_owner.fetchval("select moved_count from categories.plan where id = $1", plan_id) == 2


async def test_given_a_plan_that_is_not_applied_when_the_removal_runs_then_the_count_stays_zero(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await scheduled_plan(cat_owner, moves=2)
    await store.finish_item(plan_id, "m0", ItemState.APPLIED, None)

    await store.remove_applied_items(plan_id)

    assert await cat_owner.fetchval("select moved_count from categories.plan where id = $1", plan_id) == 0


async def test_given_the_agent_when_it_writes_the_count_itself_then_the_database_refuses(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await scheduled_plan(cat_owner, moves=1)

    try:
        await cat_agent.execute("update categories.plan set moved_count = 99")
    except asyncpg.PostgresError as error:
        assert error.sqlstate == "42501"
    else:
        raise AssertionError("the agent wrote moved_count")


async def test_given_the_api_when_it_reads_then_the_count_and_the_apply_settings_are_readable_and_not_writable(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await scheduled_plan(cat_owner, moves=1)
    await cat_owner.execute(
        "insert into categories.apply_config (mailbox_id, threshold, delay_minutes) values ($1, 50, 15)", MAILBOX
    )

    assert await cat_api.fetchval("select moved_count from categories.plan") == 0
    row = await cat_api.fetchrow("select threshold, delay_minutes from categories.apply_config")
    assert row is not None
    assert (row["threshold"], row["delay_minutes"]) == (50, 15)
    for statement in (
        "update categories.apply_config set threshold = 1",
        "insert into categories.apply_config (mailbox_id, threshold, delay_minutes) values ('x', 1, 1)",
        "delete from categories.apply_config",
    ):
        try:
            await cat_api.execute(statement)
        except asyncpg.PostgresError as error:
            assert error.sqlstate == "42501", statement
        else:
            raise AssertionError(statement)


async def test_given_0022_when_run_down_and_up_then_the_column_goes_and_comes_back_and_the_function_stays(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0021")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        column = "select count(*) from information_schema.columns where table_name = 'plan' and column_name = $1"
        assert await connection.fetchval(column, "moved_count") == 0

        await asyncio.to_thread(command.upgrade, config, "0022")
        assert await connection.fetchval(column, "moved_count") == 1

        await asyncio.to_thread(command.downgrade, config, "0021")
        assert await connection.fetchval(column, "moved_count") == 0
        assert await connection.fetchval("select count(*) from pg_proc where proname = 'remove_applied_items'") == 1

        await asyncio.to_thread(command.upgrade, config, "0022")
        assert await connection.fetchval(column, "moved_count") == 1
        grantees = {AGENT_ROLE, API_ROLE}
        assert grantees  # the roles exist in the migrated database; the rights are asserted above
    finally:
        await connection.close()
