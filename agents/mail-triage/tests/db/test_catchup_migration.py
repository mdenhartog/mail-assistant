"""U-backlog-01: migration 0003 adds the catch-up state and the backlog flag (INT-003, AC-B4, AC-B5)."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.db.conftest import alembic_config


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _migrate(url: str, revision: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), revision)


async def _downgrade(url: str, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(url), revision)


async def _fetch(url: str, sql: str) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(_plain(url))
    try:
        return await connection.fetch(sql)
    finally:
        await connection.close()


async def test_given_mail_at_revision_0002_when_upgraded_then_the_table_exists_and_old_mail_is_not_backlog(
    database_url: str,
) -> None:
    await _migrate(database_url, "0002")
    connection = await asyncpg.connect(_plain(database_url))
    try:
        await connection.execute(
            "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) "
            "values ('m1', 't1', false, now()), ('m2', 't2', true, now())"
        )
    finally:
        await connection.close()

    await _migrate(database_url, "head")

    tables = {
        r["tablename"] for r in await _fetch(database_url, "select tablename from pg_tables where schemaname='public'")
    }
    assert "catchup_state" in tables
    rows = await _fetch(database_url, "select gmail_message_id, backlog from mail_item order by id")
    assert [(r["gmail_message_id"], r["backlog"]) for r in rows] == [("m1", False), ("m2", False)]


async def test_given_revision_0003_when_downgraded_then_the_table_and_column_are_gone_and_mail_is_kept(
    database_url: str,
) -> None:
    await _migrate(database_url, "head")
    connection = await asyncpg.connect(_plain(database_url))
    try:
        await connection.execute(
            "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) values ('m1', 't1', false, now())"
        )
    finally:
        await connection.close()

    await _downgrade(database_url, "0002")

    tables = {
        r["tablename"] for r in await _fetch(database_url, "select tablename from pg_tables where schemaname='public'")
    }
    assert "catchup_state" not in tables
    columns = {
        r["column_name"]
        for r in await _fetch(
            database_url, "select column_name from information_schema.columns where table_name='mail_item'"
        )
    }
    assert "backlog" not in columns
    assert len(await _fetch(database_url, "select 1 from mail_item")) == 1


async def test_given_all_migrations_when_compared_with_the_models_then_there_is_no_drift(database_url: str) -> None:
    await _migrate(database_url, "head")
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            diff = await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"include_schemas": True}), Base.metadata
                )
            )
    finally:
        await engine.dispose()

    assert diff == []


async def test_given_the_catch_up_table_when_a_second_row_is_added_then_the_database_refuses_it(
    database_url: str,
) -> None:
    await _migrate(database_url, "head")
    connection = await asyncpg.connect(_plain(database_url))
    try:
        await connection.execute("insert into catchup_state (id, started_at) values (1, now())")
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute("insert into catchup_state (id, started_at) values (2, now())")
    finally:
        await connection.close()
