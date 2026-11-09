"""U-quiet-hours-04: migration 0004 adds the settings schema, the conversation row and alert.release_at.

Covers ADR-0025 and ADR-0026, AC-30 and AC-34 of INT-002 against a real PostgreSQL.
"""

from __future__ import annotations

import asyncio

import asyncpg
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


async def _execute(url: str, sql: str) -> None:
    connection = await asyncpg.connect(_plain(url))
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


_SEED_ALERTS = (
    "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) values ('m1', 't1', true, now()); "
    "insert into alert (mail_item_id, state, due_at, awaiting_input, created_at, updated_at) "
    "select id, 'held', now(), 'snooze', now(), now() from mail_item"
)


async def test_given_revision_0003_with_alerts_when_migrated_then_tables_exist_and_alerts_keep_their_data(
    database_url: str,
) -> None:
    await _migrate(database_url, "0003")
    await _execute(database_url, _SEED_ALERTS)

    await _migrate(database_url, "head")

    tables = {
        (r["table_schema"], r["table_name"])
        for r in await _fetch(database_url, "select table_schema, table_name from information_schema.tables")
    }
    assert {("settings", "schedule"), ("settings", "settings_change"), ("public", "conversation")} <= tables
    rows = await _fetch(database_url, "select state, awaiting_input, release_at from alert")
    assert [(r["state"], r["awaiting_input"], r["release_at"]) for r in rows] == [("held", "snooze", None)]


async def test_given_the_migration_when_downgraded_then_schema_tables_and_column_are_gone_and_data_is_kept(
    database_url: str,
) -> None:
    await _migrate(database_url, "head")
    await _execute(database_url, _SEED_ALERTS)

    before = {
        r["schema_name"] for r in await _fetch(database_url, "select schema_name from information_schema.schemata")
    }
    assert "settings" in before

    await _downgrade(database_url, "0003")

    schemas = {
        r["schema_name"] for r in await _fetch(database_url, "select schema_name from information_schema.schemata")
    }
    assert "settings" not in schemas
    tables = {r["tablename"] for r in await _fetch(database_url, "select tablename from pg_tables")}
    assert "conversation" not in tables
    columns = {
        r["column_name"]
        for r in await _fetch(
            database_url, "select column_name from information_schema.columns where table_name='alert'"
        )
    }
    assert "release_at" not in columns
    assert "awaiting_input" in columns
    assert await _fetch(database_url, "select 1 from pg_proc where proname = 'settings_audit'") == []
    rows = await _fetch(database_url, "select state, awaiting_input from alert")
    assert [(r["state"], r["awaiting_input"]) for r in rows] == [("held", "snooze")]


async def test_given_a_fresh_database_when_all_migrations_run_then_the_models_match_the_schema(
    database_url: str,
) -> None:
    assert {"settings.schedule", "settings.settings_change", "conversation"} <= set(Base.metadata.tables)
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


async def test_given_settings_change_when_its_columns_are_inspected_then_via_and_by_are_limited_and_no_free_text(
    migrated_url: str,
) -> None:
    rows = await _fetch(
        migrated_url,
        "select column_name, data_type, character_maximum_length from information_schema.columns "
        "where table_schema='settings' and table_name='settings_change'",
    )

    columns = {r["column_name"]: (r["data_type"], r["character_maximum_length"]) for r in rows}
    assert set(columns) == {"at", "via", "by", "old", "new"}
    assert columns["via"][1] is not None
    assert columns["by"][1] is not None
    assert {data_type for data_type, _ in columns.values()} <= {
        "timestamp with time zone",
        "character varying",
        "jsonb",
    }
