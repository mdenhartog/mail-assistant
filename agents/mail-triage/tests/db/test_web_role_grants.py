"""U-web-settings-07: the web role of ADR-0033 has exactly the rights of app/db/grants.sql, per table and column."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

GRANTS = Path(__file__).resolve().parents[2] / "app" / "db" / "grants.sql"
WEB = "web_settings_runtime"
AGENT = "mail_triage_runtime"
# Roles are cluster-wide: use the same throwaway passwords as the other db tests that create them.
PASSWORDS = {WEB: "web-test-password", AGENT: "runtime-test-only"}
ACTOR = "web:" + "ab" * 16

_CREATE_ROLES = f"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{WEB}') THEN
        CREATE ROLE {WEB} LOGIN PASSWORD '{PASSWORDS[WEB]}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{AGENT}') THEN
        CREATE ROLE {AGENT} LOGIN PASSWORD '{PASSWORDS[AGENT]}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$
"""

_FIRST_ROW = (  # fixed test literals, no input
    "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, updated_by) "
    f"values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', '{ACTOR}')"
)
_UPDATE = f"update settings.schedule set quiet_start = 660, version = 2, updated_via = 'web', updated_by = '{ACTOR}'"


async def _connect(migrated_url: str, role: str) -> asyncpg.Connection:
    url = make_url(migrated_url)
    return await asyncpg.connect(
        host=url.host, port=url.port, user=role, password=PASSWORDS[role], database=url.database
    )


@pytest.fixture
async def owner(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """The owner (the container's superuser) with both roles created and the grants applied."""
    connection = await asyncpg.connect(migrated_url.replace("postgresql+asyncpg://", "postgresql://"))
    await connection.execute(_CREATE_ROLES)
    await connection.execute(GRANTS.read_text(encoding="utf-8"))
    yield connection
    await connection.close()


@pytest.fixture
async def web(owner: asyncpg.Connection, migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect(migrated_url, WEB)
    yield connection
    await connection.close()


@pytest.fixture
async def agent(owner: asyncpg.Connection, migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect(migrated_url, AGENT)
    yield connection
    await connection.close()


async def _refused(connection: asyncpg.Connection, statement: str) -> str | None:
    try:
        await connection.execute(statement)
    except asyncpg.PostgresError as error:
        return error.sqlstate
    return None


async def test_given_the_web_role_when_it_inserts_selects_and_updates_the_allowed_columns_then_each_works(
    web: asyncpg.Connection, owner: asyncpg.Connection
) -> None:
    await web.execute(_FIRST_ROW)
    await web.execute(_UPDATE)
    await web.execute(
        "update settings.schedule set zone = 'UTC', quiet_end = 960, overview_at = 1020, remind_at = 480, "
        f"version = 3, updated_via = 'web', updated_by = '{ACTOR}'"
    )

    assert await web.fetchval("select quiet_start from settings.schedule") == 660
    assert await owner.fetchval("select count(*) from settings.settings_change") == 3
    assert await web.fetchval("select settings.contract_version()") == 1


@pytest.mark.parametrize(
    "statement",
    [
        "update settings.schedule set id = 2",
        "update settings.schedule set updated_at = now()",
        "delete from settings.schedule",
        "truncate settings.schedule",
    ],
)
async def test_given_the_web_role_when_it_goes_beyond_the_allowed_columns_then_postgres_refuses_it(
    web: asyncpg.Connection, statement: str
) -> None:
    await web.execute(_FIRST_ROW)

    assert await _refused(web, statement) == "42501"


@pytest.mark.parametrize(
    "table",
    [
        "mail_item",
        "alert",
        "draft",
        "oauth_token",
        "audit_log",
        "poll_state",
        "catchup_state",
        "overview_log",
        "conversation",
        "alembic_version",
        "web_notice_token",
    ],
)
async def test_given_the_web_role_when_it_selects_from_public_then_postgres_refuses_it(
    web: asyncpg.Connection, table: str
) -> None:
    assert await _refused(web, f"select * from public.{table}") == "42501"  # fixed test names


@pytest.mark.parametrize(
    "statement",
    [
        "select * from settings.settings_change",
        "insert into settings.settings_change (via, by, new) values ('web', 'x', '{}')",
        "update settings.settings_change set via = 'web'",
        "delete from settings.settings_change",
        "truncate settings.settings_change",
    ],
)
async def test_given_the_web_role_when_it_touches_settings_change_then_postgres_refuses_it(
    web: asyncpg.Connection, statement: str
) -> None:
    assert await _refused(web, statement) == "42501"


@pytest.mark.parametrize(
    "statement",
    [
        "create table settings.evil (id int)",
        "create table web_auth.evil (id int)",
        "create table public.evil (id int)",
        "create schema evil",
        "alter table settings.schedule drop constraint ck_schedule_single_row",
        "drop table settings.schedule",
        "alter table settings.schedule disable trigger schedule_audit",
        "set session_replication_role = replica",
    ],
)
async def test_given_the_web_role_when_it_tries_ddl_or_to_bypass_triggers_then_postgres_refuses_it(
    web: asyncpg.Connection, statement: str
) -> None:
    assert await _refused(web, statement) == "42501"


async def test_given_the_web_role_when_it_works_the_web_auth_tables_then_it_has_the_planned_rights(
    web: asyncpg.Connection,
) -> None:
    await web.execute(
        "insert into web_auth.login_request (id, username_key, code_hash, expires_at, created_at) "
        f"values ('r1', '{'a' * 64}', '{'b' * 64}', now(), now())"
    )
    await web.execute("update web_auth.login_request set attempts = 1")
    await web.execute(
        "insert into web_auth.session (id_hash, username_hash, last_seen_at, absolute_expires_at) "
        f"values ('{'c' * 64}', '{'d' * 64}', now(), now())"
    )
    await web.execute("update web_auth.session set last_seen_at = now()")
    await web.execute(
        'insert into web_auth.security_event (kind, result, request_id, client_key, "window") '
        "values ('session_start', 'ok', 'q1', 'k1', 1)"
    )

    assert await web.fetchval("select count(*) from web_auth.security_event") == 1
    assert await web.fetchval("select count(*) from web_auth.web_lock") == 0
    await web.execute("delete from web_auth.session")
    await web.execute("delete from web_auth.login_request")


@pytest.mark.parametrize(
    "statement",
    [
        "insert into web_auth.web_lock (id, locked_at) values (1, now())",
        "update web_auth.web_lock set locked_at = now()",
        "delete from web_auth.web_lock",
        "update web_auth.security_event set result = 'ok'",
        "delete from web_auth.security_event",
        "truncate web_auth.security_event",
        "truncate web_auth.session",
        "truncate web_auth.login_request",
    ],
)
async def test_given_the_web_role_when_it_goes_beyond_its_web_auth_rights_then_postgres_refuses_it(
    web: asyncpg.Connection, statement: str
) -> None:
    assert await _refused(web, statement) == "42501"


async def test_given_the_web_role_when_its_table_privileges_are_listed_then_only_the_planned_tables_appear(
    web: asyncpg.Connection, owner: asyncpg.Connection
) -> None:
    rows = await owner.fetch(
        "select table_schema, table_name from information_schema.role_table_grants where grantee = $1", WEB
    )

    assert {(r["table_schema"], r["table_name"]) for r in rows} <= {
        ("settings", "schedule"),
        ("web_auth", "login_request"),
        ("web_auth", "session"),
        ("web_auth", "security_event"),
        ("web_auth", "web_lock"),
    }


async def test_given_the_agent_role_when_it_inserts_and_updates_the_web_lock_then_it_works(
    agent: asyncpg.Connection,
) -> None:
    await agent.execute("insert into web_auth.web_lock (id, locked_at) values (1, now())")
    await agent.execute("update web_auth.web_lock set locked_at = now()")

    assert await agent.fetchval("select count(*) from web_auth.web_lock") == 1

    await agent.execute("delete from web_auth.web_lock")  # lifting the lock: only a Telegram command does this

    assert await agent.fetchval("select count(*) from web_auth.web_lock") == 0


@pytest.mark.parametrize(
    "statement",
    [
        "select * from web_auth.session",
        "select * from web_auth.login_request",
        "select * from web_auth.security_event",
        'insert into web_auth.security_event (kind, result, request_id, client_key, "window") '
        "values ('session_start', 'ok', 'q1', 'k1', 1)",
        "delete from web_auth.session",
        "update web_auth.login_request set attempts = 1",
        "truncate web_auth.web_lock",
        "create table web_auth.evil (id int)",
    ],
)
async def test_given_the_agent_role_when_it_goes_beyond_the_web_lock_in_web_auth_then_postgres_refuses_it(
    agent: asyncpg.Connection, statement: str
) -> None:
    assert await _refused(agent, statement) == "42501"


async def test_given_the_agent_role_when_it_works_the_notice_token_and_the_cursor_then_it_works_and_the_web_role_cannot(
    agent: asyncpg.Connection, web: asyncpg.Connection
) -> None:
    await agent.execute("insert into poll_state (id, history_id) values (1, '1')")
    await agent.execute("update poll_state set web_notice_version = 4")
    await agent.execute(
        "insert into web_notice_token (token, version, before, created_at, expires_at) "
        "values ('t1', 2, '{}', now(), now())"
    )
    await agent.execute("update web_notice_token set version = 3")

    assert await agent.fetchval("select web_notice_version from poll_state") == 4
    assert await agent.fetchval("select version from web_notice_token") == 3
    await agent.execute("delete from web_notice_token")
    assert await _refused(web, "update poll_state set web_notice_version = 9") == "42501"
    assert await _refused(web, "select * from web_notice_token") == "42501"
    assert await _refused(web, "insert into web_notice_token values ('t2', 1, '{}', now(), now())") == "42501"


async def test_given_grants_run_twice_when_the_privileges_are_compared_then_they_are_the_same(
    owner: asyncpg.Connection,
) -> None:
    tables = (
        "select grantee, table_schema, table_name, privilege_type from information_schema.role_table_grants "
        "where grantee in ($1, $2) order by 1, 2, 3, 4"
    )
    columns = (
        "select grantee, table_schema, table_name, column_name, privilege_type "
        "from information_schema.role_column_grants where grantee in ($1, $2) order by 1, 2, 3, 4, 5"
    )
    first = (await owner.fetch(tables, WEB, AGENT), await owner.fetch(columns, WEB, AGENT))

    await owner.execute(GRANTS.read_text(encoding="utf-8"))
    second = (await owner.fetch(tables, WEB, AGENT), await owner.fetch(columns, WEB, AGENT))

    assert first == second
    assert first[0]
