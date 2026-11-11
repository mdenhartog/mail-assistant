"""U-quiet-hours-04 and 16a: migrations 0004 and 0006: the settings schema, the guard trigger, the conversation row.

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


# The column is gone at head (0005): an alert is seeded without it.
_SEED_ALERTS_WITHOUT_QUESTION = (
    "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) values ('m1', 't1', true, now()); "
    "insert into alert (mail_item_id, state, due_at, created_at, updated_at) "
    "select id, 'held', now(), now(), now() from mail_item"
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
    rows = await _fetch(database_url, "select state, release_at from alert")
    assert [(r["state"], r["release_at"]) for r in rows] == [("held", None)]


async def test_given_the_migration_when_downgraded_then_schema_tables_and_column_are_gone_and_data_is_kept(
    database_url: str,
) -> None:
    await _migrate(database_url, "head")
    await _execute(database_url, _SEED_ALERTS_WITHOUT_QUESTION)

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
    assert [(r["state"], r["awaiting_input"]) for r in rows] == [("held", None)]


async def test_given_a_fresh_database_when_all_migrations_run_then_the_models_match_the_schema(
    database_url: str,
) -> None:
    assert {
        "settings.schedule",
        "settings.settings_change",
        "conversation",
        "web_auth.login_request",
        "web_auth.session",
        "web_auth.security_event",
        "web_auth.web_lock",
        "web_notice_token",
    } <= set(Base.metadata.tables)
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
    assert set(columns) == {"at", "via", "by", "db_role", "old", "new"}
    assert columns["db_role"][1] is not None
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
    await connection.execute(
        "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, "
        "updated_via, updated_by)"
        " values ($1, $2, $3, $4, $5, $6, $7, $8)",
        *(row[key] for key in _VALID_ROW),
    )


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


_SEED_SCHEDULE = (
    "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, updated_by) "
    "values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', 'u1')"
)


async def test_given_settings_written_before_0006_when_upgraded_then_rows_and_audit_records_stay_valid(
    database_url: str,
) -> None:
    await _migrate(database_url, "0004")
    await _execute(database_url, _SEED_SCHEDULE)

    await _migrate(database_url, "head")

    schedule = await _fetch(database_url, "select version, updated_via, updated_by from settings.schedule")
    changes = await _fetch(database_url, "select via, by, db_role, new from settings.settings_change")
    assert [(r["version"], r["updated_via"], r["updated_by"]) for r in schedule] == [(1, "web", "u1")]
    assert [(r["via"], r["by"], r["db_role"]) for r in changes] == [("web", "u1", "unknown")]  # recorded before 0006
    assert json.loads(changes[0]["new"])["version"] == 1
    await _execute(database_url, "update settings.schedule set quiet_start = 660, version = 2, updated_by = '42'")
    assert len(await _fetch(database_url, "select 1 from settings.settings_change")) == 2


async def test_given_0006_when_downgraded_and_upgraded_again_then_it_round_trips_and_keeps_the_data(
    database_url: str,
) -> None:
    await _migrate(database_url, "head")
    await _execute(database_url, _SEED_SCHEDULE)

    await _downgrade(database_url, "0005")

    columns = {
        r["column_name"]
        for r in await _fetch(
            database_url,
            "select column_name from information_schema.columns "
            "where table_schema='settings' and table_name='settings_change'",
        )
    }
    assert columns == {"at", "via", "by", "old", "new"}
    assert await _fetch(database_url, "select 1 from pg_proc where proname = 'schedule_guard'") == []
    # Back to the 0004 rules: the audit trigger still records a write.
    await _execute(database_url, "update settings.schedule set quiet_start = 660, version = 2")
    assert len(await _fetch(database_url, "select 1 from settings.settings_change")) == 2

    await _migrate(database_url, "head")

    assert len(await _fetch(database_url, "select 1 from settings.schedule")) == 1
    assert len(await _fetch(database_url, "select 1 from settings.settings_change where db_role is not null")) == 2


@pytest.mark.parametrize(
    "statement",
    [
        "update settings.schedule set quiet_start = 660",
        "update settings.schedule set quiet_start = 660, version = 1",
        "update settings.schedule set quiet_start = 660, version = 3",
    ],
)
async def test_given_a_schedule_update_without_a_version_step_of_one_when_run_then_the_trigger_refuses_it(
    migrated_url: str, statement: str
) -> None:
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        await _insert_schedule(connection)
        with pytest.raises(asyncpg.PostgresError) as refused:
            await connection.execute(statement)
    finally:
        await connection.close()

    assert refused.value.sqlstate == "42501"
    assert "version" in refused.value.message


async def test_given_an_update_when_it_succeeds_then_the_server_sets_updated_at_and_records_the_session_user(
    migrated_url: str,
) -> None:
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        await _insert_schedule(connection)
        await connection.execute(
            "update settings.schedule set quiet_start = 660, version = 2, updated_at = '2001-01-01 00:00:00+00'"
        )
        stamp = await connection.fetchval("select updated_at from settings.schedule")
        roles = await connection.fetch("select db_role from settings.settings_change")
        session_user = await connection.fetchval("select session_user")
    finally:
        await connection.close()

    assert stamp.year >= 2026  # the clock of the server, not the client's value
    assert [r["db_role"] for r in roles] == [session_user, session_user]
