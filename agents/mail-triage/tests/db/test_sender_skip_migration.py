"""U-label-structure-36: revision 0027, the skipped-sender counts, their rights and their retention (ADR-0054)."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import asyncpg
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.db.conftest import alembic_config, plain_url

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


async def _tables(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch("select tablename from pg_tables where schemaname = 'categories'")
    return {r["tablename"] for r in rows}


async def test_given_0027_when_upgraded_downgraded_and_upgraded_again_then_the_table_comes_goes_and_no_drift(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0026")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        assert "sender_skip" not in await _tables(connection)
        await asyncio.to_thread(command.upgrade, config, "0027")
        assert "sender_skip" in await _tables(connection)

        await asyncio.to_thread(command.downgrade, config, "0026")
        assert "sender_skip" not in await _tables(connection)
        purge = await connection.fetchval("select pg_get_functiondef('categories.purge_expired()'::regprocedure)")
        assert "sender_skip" not in purge  # the retention step goes with the table

        await asyncio.to_thread(command.upgrade, config, "0027")
        assert "sender_skip" in await _tables(connection)
    finally:
        await connection.close()

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:

            def diff(sync: Connection) -> list[object]:
                context = MigrationContext.configure(sync, opts={"include_schemas": True})
                return [d for d in compare_metadata(context, Base.metadata) if "sender_skip" in str(d)]

            assert await conn.run_sync(diff) == []
    finally:
        await engine.dispose()


async def test_given_the_roles_when_they_use_sender_skip_then_web_reads_only_and_old_rows_are_purged(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    insert = "insert into categories.sender_skip (mailbox_id, entry, skipped, last_skipped_at) values ($1, $2, 1, $3)"
    await cat_agent.execute(insert, "mb1", "old.example", datetime(2020, 1, 1, tzinfo=UTC))
    await cat_agent.execute("insert into categories.sender_skip (mailbox_id, entry) values ('mb1', 'new.example')")

    assert await cat_api.fetchval("select count(*) from categories.sender_skip") == 2
    for statement in (
        "insert into categories.sender_skip (mailbox_id, entry) values ('mb1', 'x')",
        "update categories.sender_skip set skipped = 5",
        "delete from categories.sender_skip",
    ):
        try:
            await cat_api.execute(statement)
        except asyncpg.InsufficientPrivilegeError:
            continue
        raise AssertionError(statement)

    removed = json.loads(str(await cat_agent.fetchval("select categories.purge_expired()")))

    assert removed["sender_skip"] == 1
    rows = await cat_owner.fetch("select entry from categories.sender_skip")
    assert [r["entry"] for r in rows] == ["new.example"]
