"""U-label-structure-32, criteria 1, 3 and 4: revision 0025 drops ``filing.category_id`` and the bridge (ADR-0053)."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import asyncpg
from alembic import command

from tests.db.conftest import alembic_config, plain_url

if TYPE_CHECKING:
    from alembic.config import Config

BRIDGED = "0024"
BRIDGE = "filing_topic_bridge"


async def _up(config: Config, revision: str = "head") -> None:
    await asyncio.to_thread(command.upgrade, config, revision)


async def _down(config: Config, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, config, revision)


async def _columns(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch(
        "select column_name from information_schema.columns where table_schema = 'categories' and table_name = 'filing'"
    )
    return {r["column_name"] for r in rows}


async def _bridge_objects(connection: asyncpg.Connection) -> tuple[int, int]:
    """How many triggers and functions of the bridge exist."""
    triggers: int = await connection.fetchval("select count(*) from pg_trigger where tgname = $1", BRIDGE) or 0
    functions: int = await connection.fetchval("select count(*) from pg_proc where proname = $1", BRIDGE) or 0
    return triggers, functions


async def _filing(connection: asyncpg.Connection, message: str) -> asyncpg.Record:
    row = await connection.fetchrow("select * from categories.filing where message_id = $1", message)
    assert row is not None
    return row


async def _seed_bridged(connection: asyncpg.Connection) -> uuid.UUID:
    """A mail filed by the old code (category_id only; the bridge fills topic_id)."""
    identity = uuid.uuid4()
    await connection.execute("insert into categories.mailbox (id) values ('mb')")
    await connection.execute(
        "insert into categories.filing (mailbox_id, message_id, list_version, category_id) values ('mb', 'old', 1, $1)",
        identity,
    )
    return identity


async def test_given_filings_when_0025_runs_then_category_id_and_the_bridge_are_gone_and_topic_id_stays(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await _up(config, BRIDGED)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        identity = await _seed_bridged(connection)
        assert await _bridge_objects(connection) == (1, 1)

        await _up(config)

        columns = await _columns(connection)
        assert "category_id" not in columns
        assert {"topic_id", "extra_id", "source", "source_ref"} <= columns
        assert await _bridge_objects(connection) == (0, 0)
        row = await _filing(connection, "old")
        assert (row["topic_id"], row["extra_id"], row["source"], row["source_ref"]) == (identity, None, "model", None)
    finally:
        await connection.close()


async def test_given_0025_when_it_is_downgraded_then_category_id_is_back_with_every_topic_and_the_bridge_too(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await _up(config)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        late = uuid.uuid4()
        await connection.execute("insert into categories.mailbox (id) values ('mb')")
        await connection.execute(
            "insert into categories.filing (mailbox_id, message_id, list_version, topic_id) "
            "values ('mb', 'late', 1, $1)",
            late,
        )

        await _down(config, BRIDGED)

        assert "category_id" in await _columns(connection)
        assert (await _filing(connection, "late"))["category_id"] == late
        assert await _bridge_objects(connection) == (1, 1)
        again = uuid.uuid4()
        await connection.execute(
            "insert into categories.filing (mailbox_id, message_id, list_version, category_id) "
            "values ('mb', 'b', 1, $1)",
            again,
        )
        assert (await _filing(connection, "b"))["topic_id"] == again  # the bridge works again
        nullable = await connection.fetchval(
            "select is_nullable from information_schema.columns "
            "where table_schema = 'categories' and table_name = 'filing' and column_name = 'category_id'"
        )
        assert nullable == "NO"
    finally:
        await connection.close()


async def test_given_the_chain_when_it_runs_twice_up_and_down_then_nothing_changes(database_url: str) -> None:
    config = alembic_config(database_url)
    await _up(config, BRIDGED)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        identity = await _seed_bridged(connection)
        await _up(config)
        await _up(config)
        after_up = await _columns(connection)

        await _down(config, BRIDGED)
        await _up(config)

        assert await _columns(connection) == after_up
        assert (await _filing(connection, "old"))["topic_id"] == identity
        assert await _bridge_objects(connection) == (0, 0)
    finally:
        await connection.close()


async def test_given_the_agent_when_it_files_a_mail_then_it_names_topic_id_and_may_not_name_category_id(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    identity = uuid.uuid4()
    await cat_agent.execute(
        "insert into categories.filing (mailbox_id, message_id, list_version, topic_id, extra_id, source, source_ref) "
        "values ('mb1', 'x', 1, $1, null, 'model', null)",
        identity,
    )

    row = await _filing(cat_owner, "x")
    assert row["topic_id"] == identity
    assert "category_id" not in row.keys()  # noqa: SIM118  # asyncpg Record.keys() is an iterator, not a dict
    grants = await cat_owner.fetch(
        "select column_name from information_schema.column_privileges where table_schema = 'categories' "
        "and table_name = 'filing' and grantee = 'mail_triage_runtime' and privilege_type = 'INSERT'"
    )
    assert {r["column_name"] for r in grants} == {
        "mailbox_id",
        "message_id",
        "list_version",
        "topic_id",
        "extra_id",
        "source",
        "source_ref",
    }
