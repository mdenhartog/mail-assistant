"""U-web-settings-06: migration 0008: web_auth, the web line of the guard, the contract version, the notice record.

Covers AC-9, AC-17, W-8, W-10, W-13, W-15 of INT-002 and ADR-0033 against a real PostgreSQL. Grants are not part of this
unit (U-07); the tests that need the web role grant it what they use, inside the test database only.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.db.conftest import alembic_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

WEB_ROLE = "web_settings_runtime"
WEB_PASSWORD = "web-test-password"  # noqa: S105  # a throwaway role in a throwaway container
GOOD_ACTOR = "web:" + "0123456789abcdef" * 2
HASH = "a" * 64

_SEED_SCHEDULE = (
    "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, updated_by) "
    "values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'telegram', '42')"
)


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


async def _create_web_role(url: str) -> None:
    """The login role of the web api, with just enough rights on the schedule for the guard tests."""
    connection = await asyncpg.connect(_plain(url))
    try:
        exists = await connection.fetchval("select 1 from pg_roles where rolname = $1", WEB_ROLE)
        if not exists:
            await connection.execute(f"CREATE ROLE {WEB_ROLE} LOGIN PASSWORD '{WEB_PASSWORD}'")  # noqa: S608
        await connection.execute(f"GRANT USAGE ON SCHEMA settings TO {WEB_ROLE}")
        await connection.execute(f"GRANT SELECT, INSERT, UPDATE ON settings.schedule TO {WEB_ROLE}")
    finally:
        await connection.close()


@pytest.fixture
async def web_connection(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    await _create_web_role(migrated_url)
    await _execute(migrated_url, _SEED_SCHEDULE)
    parts = urlsplit(_plain(migrated_url))
    connection = await asyncpg.connect(
        host=parts.hostname, port=parts.port, user=WEB_ROLE, password=WEB_PASSWORD, database=parts.path.lstrip("/")
    )
    try:
        yield connection
    finally:
        await connection.close()


_WEB_UPDATE = (
    "update settings.schedule set quiet_start = 660, version = {version}, updated_via = '{via}', updated_by = $1"
)


async def test_given_revision_0007_with_settings_data_when_migrated_then_the_web_tables_exist_without_drift(
    database_url: str,
) -> None:
    await _migrate(database_url, "0007")
    await _execute(database_url, _SEED_SCHEDULE)

    await _migrate(database_url, "0008")

    tables = {
        (r["table_schema"], r["table_name"])
        for r in await _fetch(database_url, "select table_schema, table_name from information_schema.tables")
    }
    assert {
        ("web_auth", "login_request"),
        ("web_auth", "session"),
        ("web_auth", "security_event"),
        ("web_auth", "web_lock"),
        ("public", "web_notice_token"),
    } <= tables
    columns = {
        r["column_name"]
        for r in await _fetch(database_url, "select column_name from information_schema.columns where table_name = 'poll_state'")
    }
    assert "web_notice_version" in columns
    rows = await _fetch(database_url, "select version, updated_via, updated_by, quiet_start from settings.schedule")
    assert [tuple(r.values()) for r in rows] == [(1, "telegram", "42", 600)]
    assert len(await _fetch(database_url, "select 1 from settings.settings_change")) == 1

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


async def test_given_0008_when_downgraded_then_everything_is_gone_the_old_guard_works_and_it_upgrades_again(
    database_url: str,
) -> None:
    await _migrate(database_url, "head")
    await _execute(database_url, _SEED_SCHEDULE)
    await _execute(database_url, "insert into poll_state (id, history_id, web_notice_version) values (1, '5', 3)")

    await _downgrade(database_url, "0007")

    schemas = {r["schema_name"] for r in await _fetch(database_url, "select schema_name from information_schema.schemata")}
    assert "web_auth" not in schemas
    tables = {r["tablename"] for r in await _fetch(database_url, "select tablename from pg_tables")}
    assert "web_notice_token" not in tables
    columns = {
        r["column_name"]
        for r in await _fetch(database_url, "select column_name from information_schema.columns where table_name = 'poll_state'")
    }
    assert "web_notice_version" not in columns
    assert await _fetch(database_url, "select 1 from pg_proc where proname = 'contract_version'") == []
    guard = await _fetch(database_url, "select prosrc from pg_proc where proname = 'schedule_guard'")
    assert "web" not in guard[0]["prosrc"].replace("updated_via", "")
    # The 0006 guard still works: a step of one is accepted, a step of two is refused.
    await _execute(database_url, "update settings.schedule set quiet_start = 660, version = 2, updated_via = 'telegram'")
    with pytest.raises(asyncpg.PostgresError):
        await _execute(database_url, "update settings.schedule set quiet_start = 661, version = 4")

    await _migrate(database_url, "head")

    assert len(await _fetch(database_url, "select 1 from settings.schedule")) == 1
    assert len(await _fetch(database_url, "select 1 from settings.settings_change")) == 2
    assert [r["history_id"] for r in await _fetch(database_url, "select history_id from poll_state")] == ["5"]


async def test_given_the_web_role_when_it_updates_with_a_valid_actor_then_the_channel_is_web_and_the_audit_says_so(
    web_connection: asyncpg.Connection, migrated_url: str
) -> None:
    await web_connection.execute(_WEB_UPDATE.format(version=2, via="web"), GOOD_ACTOR)

    row = (await _fetch(migrated_url, "select updated_via, updated_by from settings.schedule"))[0]
    audit = (await _fetch(migrated_url, "select via, by, db_role, new from settings.settings_change order by new->>'version'"))[-1]
    assert (row["updated_via"], row["updated_by"]) == ("web", GOOD_ACTOR)
    assert (audit["via"], audit["by"], audit["db_role"]) == ("web", GOOD_ACTOR, WEB_ROLE)
    assert json.loads(audit["new"])["version"] == 2


@pytest.mark.parametrize(
    "actor",
    ["telegram:1", "web:" + "0123456789abcdef" * 2 + "0", ("web:" + "0123456789abcdef" * 2)[:-1], "web:" + "0123456789ABCDEF" * 2, ""],
)
async def test_given_the_web_role_when_updated_by_is_not_a_web_actor_then_42501(
    web_connection: asyncpg.Connection, actor: str
) -> None:
    with pytest.raises(asyncpg.PostgresError) as refused:
        await web_connection.execute(_WEB_UPDATE.format(version=2, via="web"), actor)

    assert refused.value.sqlstate == "42501"


async def test_given_the_web_role_when_it_skips_a_version_then_42501(web_connection: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.PostgresError) as refused:
        await web_connection.execute(_WEB_UPDATE.format(version=3, via="web"), GOOD_ACTOR)

    assert refused.value.sqlstate == "42501"


async def test_given_the_web_role_when_it_claims_telegram_then_42501(web_connection: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.PostgresError) as refused:
        await web_connection.execute(_WEB_UPDATE.format(version=2, via="telegram"), GOOD_ACTOR)

    assert refused.value.sqlstate == "42501"


async def test_given_the_agent_role_and_the_owner_when_they_write_then_the_0006_rules_still_hold(
    migrated_url: str,
) -> None:
    await _execute(migrated_url, _SEED_SCHEDULE)
    # The owner keeps the channel it claims and any actor text.
    await _execute(
        migrated_url, "update settings.schedule set quiet_start = 660, version = 2, updated_via = 'web', updated_by = 'x'"
    )
    with pytest.raises(asyncpg.PostgresError) as skipped:
        await _execute(migrated_url, "update settings.schedule set quiet_start = 670, version = 4")

    assert skipped.value.sqlstate == "42501"


async def test_given_the_contract_version_when_called_then_it_is_an_integer_and_no_new_function_is_public(
    migrated_url: str,
) -> None:
    version = (await _fetch(migrated_url, "select settings.contract_version() as v"))[0]["v"]
    assert isinstance(version, int)
    assert version >= 1

    public_executable = await _fetch(
        migrated_url,
        "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname in ('settings', 'web_auth') "
        "and has_function_privilege('public', p.oid, 'EXECUTE')",
    )
    assert public_executable == []
    functions = await _fetch(
        migrated_url,
        "select p.proname, p.proconfig from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'settings' and p.proname = 'contract_version'",
    )
    assert any("search_path" in c for c in functions[0]["proconfig"])


async def test_given_the_web_tables_when_their_columns_are_inspected_then_they_are_bounded_and_checked(
    migrated_url: str,
) -> None:
    rows = await _fetch(
        migrated_url,
        "select table_name, column_name, data_type, character_maximum_length from information_schema.columns "
        "where table_schema = 'web_auth'",
    )
    assert {r["data_type"] for r in rows} <= {
        "character",
        "character varying",
        "smallint",
        "integer",
        "bigint",
        "timestamp with time zone",
        "boolean",
    }
    assert all(r["character_maximum_length"] is not None for r in rows if r["data_type"].startswith("char"))
    lengths = {(r["table_name"], r["column_name"]): r["character_maximum_length"] for r in rows}
    for key in [("login_request", "code_hash"), ("login_request", "username_key"), ("session", "id_hash"), ("session", "username_hash")]:
        assert lengths[key] == 64

    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "insert into web_auth.security_event (kind, result, request_id, client_key, \"window\") "
                "values ('free text', 'ok', 'r', 'c', 1)"
            )
        with pytest.raises(asyncpg.DataError):
            await connection.execute(
                "insert into web_auth.login_request (id, username_key, code_hash, expires_at, created_at) "
                "values ('a', $1, $1, now(), now())",
                "short" * 20,
            )
        await connection.execute(
            "insert into web_auth.login_request (id, username_key, code_hash, expires_at, created_at, attempts) "
            "values ('a', $1, $1, now(), now(), 5)",
            HASH,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "insert into web_auth.login_request (id, username_key, code_hash, expires_at, created_at, attempts) "
                "values ('b', $1, $1, now(), now(), 6)",
                HASH,
            )
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "insert into web_auth.login_request (id, username_key, code_hash, expires_at, created_at, attempts) "
                "values ('c', $1, $1, now(), now(), -1)",
                HASH,
            )
    finally:
        await connection.close()


async def test_given_web_lock_when_a_second_row_is_inserted_then_it_is_refused(migrated_url: str) -> None:
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        await connection.execute("insert into web_auth.web_lock (id, locked_at) values (1, now())")
        with pytest.raises(asyncpg.PostgresError) as refused:
            await connection.execute("insert into web_auth.web_lock (id, locked_at) values (2, now())")
    finally:
        await connection.close()

    assert refused.value.sqlstate in {"23505", "23514"}


async def test_given_the_notice_token_record_when_the_same_token_is_inserted_twice_then_the_second_is_refused(
    migrated_url: str,
) -> None:
    sql = (
        "insert into web_notice_token (token, version, before, created_at, expires_at) "
        "values ('t1', 2, '{}'::jsonb, now(), now())"
    )
    connection = await asyncpg.connect(_plain(migrated_url))
    try:
        await connection.execute(sql)
        with pytest.raises(asyncpg.UniqueViolationError):
            await connection.execute(sql)
    finally:
        await connection.close()
