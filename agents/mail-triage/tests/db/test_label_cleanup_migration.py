"""U-label-prefix-removal-09, criteria 7 and 8: the waiting time stored with a timer and the purge of the records.

Revision 0030 is unreleased, so it is edited in place: ``label_empty_since.wait_minutes`` (5 to 720) and the function
``categories.purge_label_records()`` that removes ``deleted_label`` and ``label_rename_item`` rows older than the
retention (``settings.schedule.label_retention_days``, 30 days while there is no row).
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from alembic import command

from tests.db.conftest import alembic_config, plain_url
from tests.db.plan_support import sqlstate_of

HASH_OLD = "a" * 64
HASH_NEW = "b" * 64
PURGE = "select categories.purge_label_records()"
TIMER = (
    "insert into categories.label_empty_since (mailbox_id, label_id, empty_since, last_seen_empty, wait_minutes) "
    "values ('mb1', 'L1', now(), now(), $1)"
)


async def test_given_the_agent_when_it_stores_a_timer_then_the_wait_is_kept_and_must_be_5_to_720(
    cat_agent: asyncpg.Connection,
) -> None:
    await cat_agent.execute(TIMER, 5)
    assert await cat_agent.fetchval("select wait_minutes from categories.label_empty_since") == 5
    for bad in (4, 721):
        with pytest.raises(asyncpg.CheckViolationError):
            await cat_agent.execute(TIMER.replace("'L1'", "'L2'"), bad)
    await cat_agent.execute(TIMER.replace("'L1'", "'L3'"), 720)


async def test_given_the_column_then_it_is_a_smallint_without_null_and_without_default(
    cat_owner: asyncpg.Connection,
) -> None:
    row = await cat_owner.fetchrow(
        "select data_type, is_nullable, column_default from information_schema.columns "
        "where table_schema = 'categories' and table_name = 'label_empty_since' and column_name = 'wait_minutes'"
    )
    assert row is not None
    assert (row["data_type"], row["is_nullable"], row["column_default"]) == ("smallint", "NO", None)


async def test_given_0030_ran_with_a_timer_when_it_runs_again_then_the_timer_and_its_wait_are_unchanged(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0030")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await connection.execute("insert into categories.mailbox (id) values ('mb1')")
        await connection.execute(TIMER, 45)
        before = await connection.fetch("select * from categories.label_empty_since")

        await asyncio.to_thread(command.stamp, config, "0029")
        await asyncio.to_thread(command.upgrade, config, "0030")

        assert await connection.fetch("select * from categories.label_empty_since") == before
    finally:
        await connection.close()


async def test_given_a_database_where_the_table_exists_without_the_column_when_0030_runs_then_the_column_is_added(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0030")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await connection.execute("alter table categories.label_empty_since drop column wait_minutes")

        await asyncio.to_thread(command.stamp, config, "0029")
        await asyncio.to_thread(command.upgrade, config, "0030")

        await connection.execute("insert into categories.mailbox (id) values ('mb1')")
        await connection.execute(TIMER, 720)
    finally:
        await connection.close()


async def test_given_0030_when_downgraded_then_the_purge_function_is_gone_and_up_again_it_is_back(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0030")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await asyncio.to_thread(command.downgrade, config, "0029")
        assert await connection.fetch("select 1 from pg_proc where proname = 'purge_label_records'") == []

        await asyncio.to_thread(command.upgrade, config, "0030")
        assert len(await connection.fetch("select 1 from pg_proc where proname = 'purge_label_records'")) == 1
    finally:
        await connection.close()


async def _seed(owner: asyncpg.Connection, *, retention_days: int | None) -> None:
    if retention_days is not None:
        await owner.execute(
            "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, "
            "updated_by, label_retention_days) "
            "values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', 'u1', $1)",
            retention_days,
        )
    await owner.execute(
        "insert into categories.deleted_label (mailbox_id, label_id_hash, name, deleted_at) values "
        "('mb1', $1, 'old name', now() - interval '31 days'), ('mb1', $2, 'new name', now() - interval '29 days'), "
        "('mb2', $3, 'other mailbox old', now() - interval '40 days')",
        HASH_OLD,
        HASH_NEW,
        "c" * 64,
    )
    await owner.execute("insert into categories.label_migration (mailbox_id, state) values ('mb1', 'done')")
    await owner.execute(
        "insert into categories.label_rename_item (mailbox_id, label_id, old_name, new_name, action, state, created_at)"
        " values ('mb1', 'old', 'Assistant/A', 'A', 'rename', 'done', now() - interval '31 days'), "
        "('mb1', 'new', 'Assistant/B', 'B', 'rename', 'done', now() - interval '29 days'), "
        "('mb1', 'waiting', 'Assistant/C', 'C', 'rename', 'planned', now() - interval '60 days')"
    )


async def test_given_the_default_retention_when_the_agent_purges_then_only_older_rows_go_and_a_waiting_plan_stays(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _seed(cat_owner, retention_days=None)

    await cat_agent.fetchval(PURGE)

    assert [r["name"] for r in await cat_owner.fetch("select name from categories.deleted_label order by name")] == [
        "new name"
    ]
    assert {r["label_id"] for r in await cat_owner.fetch("select label_id from categories.label_rename_item")} == {
        "new",
        "waiting",  # a plan that waits for the confirmation is the thing the hash covers: it is never purged
    }


async def test_given_a_retention_of_7_days_when_the_agent_purges_then_the_setting_decides(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _seed(cat_owner, retention_days=90)
    await cat_agent.fetchval(PURGE)
    assert await cat_owner.fetchval("select count(*) from categories.deleted_label") == 3

    await cat_owner.execute("update settings.schedule set label_retention_days = 7, version = 2")
    await cat_agent.fetchval(PURGE)

    assert await cat_owner.fetchval("select count(*) from categories.deleted_label") == 0


async def test_given_a_purge_when_run_twice_then_the_second_run_removes_nothing(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _seed(cat_owner, retention_days=None)

    await cat_agent.fetchval(PURGE)
    second = await cat_agent.fetchval(PURGE)

    assert second is not None
    assert '"deleted_label": 0' in str(second)
    assert '"label_rename_item": 0' in str(second)


async def test_given_the_purge_function_then_the_agent_may_run_it_and_the_api_and_public_may_not(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    assert await cat_owner.fetchval(
        "select has_function_privilege('mail_triage_runtime', 'categories.purge_label_records()', 'EXECUTE')"
    )
    assert not await cat_owner.fetchval(
        "select has_function_privilege('public', 'categories.purge_label_records()', 'EXECUTE')"
    )
    with pytest.raises(asyncpg.PostgresError) as caught:
        await cat_api.fetchval(PURGE)
    assert sqlstate_of(caught.value) == "42501"
