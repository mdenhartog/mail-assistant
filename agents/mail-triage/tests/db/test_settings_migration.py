"""U-quiet-hours-04: migration 0004 adds the settings schema, the conversation row and alert.release_at.

Covers ADR-0025 and ADR-0026, AC-30 and AC-34 of INT-002 against a real PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json

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


_VALID_ROW = {
    "id": 1,
    "zone": "Europe/Amsterdam",
    "quiet_start": 600,
    "quiet_end": 900,
    "overview_at": 1080,
    "remind_at": 540,
    "updated_via": "web",
    "updated_by": "u1",
}


async def _insert_schedule(connection: asyncpg.Connection, **overrides: object) -> None:
    row = _VALID_ROW | overrides
    columns = ", ".join(row)
    placeholders = ", ".join(f"${i}" for i in range(1, len(row) + 1))
    await connection.execute(f"insert into settings.schedule ({columns}) values ({placeholders})", *row.values())


@pytest.mark.parametrize(
    ("constraint", "overrides"),
    [
        ("ck_schedule_minutes_range", {"remind_at": 1440}),
        ("ck_schedule_minutes_range", {"quiet_start": -1}),
        ("ck_schedule_quiet_distinct", {"quiet_start": 600, "quiet_end": 600}),
        ("ck_schedule_window_length", {"quiet_start": 600, "quiet_end": 630}),
        ("ck_schedule_window_length", {"quiet_start": 0, "quiet_end": 781, "remind_at": 900}),
        ("ck_schedule_overview_outside", {"overview_at": 700}),
        ("ck_schedule_overview_outside", {"overview_at": 600}),
        ("ck_schedule_remind_outside", {"remind_at": 899}),
        ("ck_schedule_zone_pattern", {"zone": "Europe/Amsterdam; drop table alert"}),
        ("ck_schedule_zone_pattern", {"zone": "a/b/c/d"}),
        ("ck_schedule_updated_via", {"updated_via": "email"}),
        ("ck_schedule_single_row", {"id": 2}),
    ],
)
async def test_given_a_row_breaking_one_rule_when_inserted_directly_then_postgres_refuses_it(
    migrated_url: str, constraint: str, overrides: dict[str, object]
) -> None:
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        with pytest.raises(asyncpg.CheckViolationError) as refused:
            await _insert_schedule(connection, **overrides)
    finally:
        await connection.close()

    assert refused.value.constraint_name == constraint


async def test_given_a_window_over_midnight_and_a_time_at_its_end_when_inserted_then_it_is_accepted(
    migrated_url: str,
) -> None:
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        # 22:00-07:00 crosses midnight; 07:00 is outside (end exclusive).
        await _insert_schedule(connection, quiet_start=1320, quiet_end=420, overview_at=420, remind_at=1319)
        count = await connection.fetchval("select count(*) from settings.schedule")
    finally:
        await connection.close()

    assert count == 1


async def test_given_a_window_over_midnight_and_a_time_at_its_start_when_inserted_then_postgres_refuses_it(
    migrated_url: str,
) -> None:
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        with pytest.raises(asyncpg.CheckViolationError) as refused:
            await _insert_schedule(connection, quiet_start=1320, quiet_end=420, overview_at=1320)
    finally:
        await connection.close()

    assert refused.value.constraint_name == "ck_schedule_overview_outside"


async def test_given_the_conversation_table_when_bad_rows_are_inserted_then_postgres_refuses_them(
    migrated_url: str,
) -> None:
    sql = "insert into conversation (id, kind, step, nonce, expires_at) values ($1, $2, 's', 'n', now())"
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        await connection.execute(sql, 1, "settings")
        with pytest.raises(asyncpg.CheckViolationError) as second:
            await connection.execute(sql, 2, "snooze")
        await connection.execute("delete from conversation")
        with pytest.raises(asyncpg.CheckViolationError) as kind:
            await connection.execute(sql, 1, "other")
    finally:
        await connection.close()

    assert second.value.constraint_name == "ck_conversation_single_row"
    assert kind.value.constraint_name == "ck_conversation_kind"


async def test_given_an_insert_and_an_update_when_they_succeed_then_settings_change_records_both(
    migrated_url: str,
) -> None:
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        await _insert_schedule(connection)
        await connection.execute(
            "update settings.schedule set quiet_start = 660, version = version + 1, "
            "updated_via = 'telegram', updated_by = '42'"
        )
        records = await connection.fetch("select at, via, by, old, new from settings.settings_change order by at, via")
    finally:
        await connection.close()

    by_via = {r["via"]: r for r in records}
    assert len(records) == 2
    created, changed = by_via["web"], by_via["telegram"]
    assert created["by"] == "u1"
    assert created["old"] is None
    assert json.loads(created["new"])["quiet_start"] == 600
    assert changed["by"] == "42"
    assert json.loads(changed["old"])["quiet_start"] == 600
    assert json.loads(changed["new"])["quiet_start"] == 660
    assert changed["at"] is not None
