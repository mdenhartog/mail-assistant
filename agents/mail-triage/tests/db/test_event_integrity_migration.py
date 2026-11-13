"""U-web-settings-65: migration 0012 (contract version 2, count integrity, column grants, the (kind, at) index)."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic import command

from tests.db.conftest import alembic_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

GRANTS = Path(__file__).resolve().parents[2] / "app" / "db" / "grants.sql"
WEB_ROLE = "web_settings_runtime"
WEB_PASSWORD = "web-test-only"  # noqa: S105  # what the first test to make the shared role used (login request)
AGENT_ROLE = "mail_triage_runtime"
AGENT_PASSWORD = "agent-test-only"  # noqa: S105  # same: roles are cluster-wide and this file sorts first
CLIENT = "c" * 64
USER = "u" * 64

_ROW = (
    'insert into web_auth.security_event (kind, result, username_hash, request_id, client_key, "window", count) '
    f"values ('code_refused', 'refused', '{USER}', 'req-1', '{CLIENT}', 1, {{count}})"
)
_CREATE_ROLES = f"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{WEB_ROLE}') THEN
        CREATE ROLE {WEB_ROLE} LOGIN PASSWORD '{WEB_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{AGENT_ROLE}') THEN
        CREATE ROLE {AGENT_ROLE} LOGIN PASSWORD '{AGENT_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$
"""
_TRIGGERS = "select tgname from pg_trigger where tgrelid = 'web_auth.security_event'::regclass and not tgisinternal"
_INDEXES = "select indexname from pg_indexes where schemaname = 'web_auth' and tablename = 'security_event'"
_CHECKS = "select conname from pg_constraint where conrelid = 'web_auth.security_event'::regclass and contype = 'c'"
_FUNCTIONS = "select proname from pg_proc where proname like '%security_event%'"


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _migrate(url: str, revision: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), revision)


async def _downgrade(url: str, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(url), revision)


async def _names(url: str, sql: str) -> list[str]:
    connection = await asyncpg.connect(_plain(url))
    try:
        return [r[0] for r in await connection.fetch(sql)]
    finally:
        await connection.close()


async def _version(url: str) -> int:
    connection = await asyncpg.connect(_plain(url))
    try:
        return await connection.fetchval("select settings.contract_version()")
    finally:
        await connection.close()


@pytest.fixture
async def owner(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """The owner connection with the roles made and grants.sql applied, as the migrate job does."""
    connection = await asyncpg.connect(_plain(migrated_url))
    await connection.execute(_CREATE_ROLES)
    await connection.execute(GRANTS.read_text(encoding="utf-8"))
    yield connection
    await connection.close()


@asynccontextmanager
async def _as(connection: asyncpg.Connection, role: str) -> AsyncIterator[asyncpg.Connection]:
    """Act as a runtime role without logging in as it (the role passwords differ between test files)."""
    await connection.execute(f"set role {role}")
    try:
        yield connection
    finally:
        await connection.execute("reset role")


# Criterion 5
async def test_given_0012_when_run_up_down_and_up_then_every_part_comes_and_goes(database_url: str) -> None:
    await _migrate(database_url, "0011")
    assert await _version(database_url) == 1
    assert await _names(database_url, _TRIGGERS) == []

    await _migrate(database_url, "0012")

    assert await _version(database_url) == 2
    assert len(await _names(database_url, _TRIGGERS)) == 1
    assert "ix_security_event_kind_at" in await _names(database_url, _INDEXES)
    assert "ck_security_event_count" in await _names(database_url, _CHECKS)

    await _downgrade(database_url, "0011")

    assert await _version(database_url) == 1
    assert await _names(database_url, _TRIGGERS) == []
    assert "ix_security_event_kind_at" not in await _names(database_url, _INDEXES)
    assert "ck_security_event_count" not in await _names(database_url, _CHECKS)
    assert await _names(database_url, _FUNCTIONS) == []

    await _migrate(database_url, "0012")

    assert await _version(database_url) == 2
    assert len(await _names(database_url, _TRIGGERS)) == 1


async def test_given_0012_when_the_functions_are_inspected_then_none_is_public_and_the_path_is_pinned(
    owner: asyncpg.Connection,
) -> None:
    config = await owner.fetchval(
        "select proconfig from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'settings' and p.proname = 'contract_version'"
    )
    public = await owner.fetch(
        "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname in ('settings', 'web_auth') and has_function_privilege('public', p.oid, 'EXECUTE')"
    )
    web_can_call = await owner.fetchval(
        "select has_function_privilege($1, 'settings.contract_version()', 'EXECUTE')", WEB_ROLE
    )
    unpinned = await owner.fetch(
        "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'web_auth' and p.proconfig is null"
    )

    assert any("search_path" in c for c in config)
    assert public == []
    assert unpinned == []
    assert web_can_call


# Criterion 2
async def test_given_an_event_when_the_web_role_adds_one_then_it_works(
    owner: asyncpg.Connection,
) -> None:
    await owner.execute(_ROW.format(count=1))
    async with _as(owner, WEB_ROLE) as web:
        await web.execute("update web_auth.security_event set count = count + 1")
        await web.execute("update web_auth.security_event set count = count + 1")
        assert await web.fetchval("select count from web_auth.security_event") == 3


@pytest.mark.parametrize("new_count", ["0", "count + 2", "count", "count - 1", "1", "100000"])
async def test_given_an_event_when_the_web_role_sets_count_to_anything_but_old_plus_one_then_it_is_refused(
    owner: asyncpg.Connection, new_count: str
) -> None:
    await owner.execute(_ROW.format(count=5))
    async with _as(owner, WEB_ROLE) as web:
        with pytest.raises(asyncpg.PostgresError) as refused:
            await web.execute(f"update web_auth.security_event set count = {new_count}")
        assert refused.value.sqlstate == "42501"
        assert await web.fetchval("select count from web_auth.security_event") == 5


@pytest.mark.parametrize(
    "assignment",
    [
        "kind = 'rate_limited'",
        "client_key = repeat('e', 64)",
        "request_id = 'x'",
        "username_hash = null",
        "at = now() - interval '1 day'",
        "kind = 'rate_limited', count = count + 1",
        "id = id + 100",
    ],
)
async def test_given_an_event_when_any_other_column_changes_then_the_trigger_refuses_even_the_owner(
    owner: asyncpg.Connection, assignment: str
) -> None:
    await owner.execute(_ROW.format(count=1))

    with pytest.raises(asyncpg.PostgresError) as refused:
        await owner.execute(f"update web_auth.security_event set {assignment}")

    assert refused.value.sqlstate == "42501"


async def test_given_the_web_role_when_it_changes_another_column_then_the_grant_refuses_it(
    owner: asyncpg.Connection,
) -> None:
    await owner.execute(_ROW.format(count=1))
    async with _as(owner, WEB_ROLE) as web:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await web.execute("update web_auth.security_event set kind = 'rate_limited'")


async def test_given_a_count_below_one_when_an_event_is_inserted_then_the_check_refuses_it(
    owner: asyncpg.Connection,
) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        await owner.execute(_ROW.format(count=0))
    with pytest.raises(asyncpg.CheckViolationError):
        await owner.execute(_ROW.format(count=-1))


async def test_given_the_trigger_when_an_event_is_deleted_then_it_does_not_get_in_the_way(
    owner: asyncpg.Connection,
) -> None:
    await owner.execute(_ROW.format(count=1))
    await owner.execute("delete from web_auth.security_event")

    assert await owner.fetchval("select count(*) from web_auth.security_event") == 0


# Criterion 3
async def test_given_the_agent_role_when_it_selects_the_alert_columns_then_it_works(
    owner: asyncpg.Connection,
) -> None:
    await owner.execute(_ROW.format(count=4))
    async with _as(owner, AGENT_ROLE) as agent:
        assert await agent.fetchval("select sum(count) from web_auth.security_event where kind = 'code_refused'") == 4
        assert await agent.fetchval("select max(id) from web_auth.security_event where at <= now()") >= 1
        assert await agent.fetchval("select count(*) from web_auth.security_event") == 1


@pytest.mark.parametrize(
    "select_list",
    ["username_hash", "client_key", "request_id", "result", '"window"', "*", "id, kind, at, count, client_key"],
)
async def test_given_the_agent_role_when_it_selects_a_private_column_then_42501(
    owner: asyncpg.Connection, select_list: str
) -> None:
    await owner.execute(_ROW.format(count=1))
    async with _as(owner, AGENT_ROLE) as agent:
        with pytest.raises(asyncpg.PostgresError) as refused:
            await agent.fetch(f"select {select_list} from web_auth.security_event")
        assert refused.value.sqlstate == "42501"


async def test_given_the_agent_role_when_privileges_are_read_then_only_four_columns_are_selectable(
    owner: asyncpg.Connection,
) -> None:
    rows = await owner.fetch(
        "select column_name from information_schema.columns where table_schema = 'web_auth' "
        "and table_name = 'security_event' "
        "and has_column_privilege($1, 'web_auth.security_event', column_name, 'SELECT')",
        AGENT_ROLE,
    )

    assert {r["column_name"] for r in rows} == {"id", "kind", "at", "count"}


# Criterion 4
async def test_given_the_alert_query_on_a_large_table_when_explained_then_it_uses_the_kind_at_index(
    owner: asyncpg.Connection,
) -> None:
    await owner.execute(
        'insert into web_auth.security_event (at, kind, result, request_id, client_key, "window") '
        "select now() - (i * interval '10 seconds'), "
        "(array['code_refused','code_request_refused','csrf_refused','rate_limited','session_start','session_end',"
        "'lock_refused','mail_failed'])[1 + i % 8], 'refused', 'r' || i, md5(i::text) || md5(i::text), i "
        "from generate_series(1, 200000) as i"
    )
    await owner.execute("analyze web_auth.security_event")

    plan = json.dumps(
        json.loads(
            await owner.fetchval(
                "explain (format json) select coalesce(sum(count), 0) from web_auth.security_event "
                "where kind = 'code_refused' and at > now() - interval '1 hour' and id > 0"
            )
        )
    )

    assert "ix_security_event_kind_at" in plan
    assert "Seq Scan" not in plan


# The kind code_invalid (U-web-settings-63) and old rows
_INVALID = (
    'insert into web_auth.security_event (kind, result, request_id, client_key, "window") '
    f"values ('code_invalid', 'refused', 'req-9', '{CLIENT}', 9)"
)


async def test_given_0012_when_the_web_role_inserts_a_code_invalid_event_then_it_works_and_the_trigger_allows_it(
    owner: asyncpg.Connection,
) -> None:
    async with _as(owner, WEB_ROLE) as web:
        await web.execute(_INVALID)
        assert await web.fetchval("select count from web_auth.security_event where kind = 'code_invalid'") == 1


async def test_given_0011_when_a_code_invalid_event_is_inserted_then_the_check_refuses_it(database_url: str) -> None:
    await _migrate(database_url, "0011")
    connection = await asyncpg.connect(_plain(database_url))
    try:
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(_INVALID)
    finally:
        await connection.close()


async def test_given_a_code_invalid_row_when_0012_runs_down_and_up_then_the_row_goes_and_the_check_is_restored(
    database_url: str,
) -> None:
    await _migrate(database_url, "0012")
    connection = await asyncpg.connect(_plain(database_url))
    try:
        await connection.execute(_INVALID)
        await connection.execute(_ROW.format(count=2))
    finally:
        await connection.close()

    await _downgrade(database_url, "0011")

    kinds = await _names(database_url, "select kind from web_auth.security_event")
    assert kinds == ["code_refused"]  # the code_invalid row is deleted, the others stay
    await _migrate(database_url, "0012")
    assert await _names(database_url, "select kind from web_auth.security_event") == ["code_refused"]


async def test_given_old_rows_with_a_count_below_one_when_0012_runs_then_they_are_raised_to_one(
    database_url: str,
) -> None:
    await _migrate(database_url, "0011")
    connection = await asyncpg.connect(_plain(database_url))
    try:
        await connection.execute(_ROW.format(count=0))
    finally:
        await connection.close()

    await _migrate(database_url, "0012")

    counts = await _names(database_url, "select count::text from web_auth.security_event")
    assert counts == ["1"]
    assert len(await _names(database_url, _TRIGGERS)) == 1
