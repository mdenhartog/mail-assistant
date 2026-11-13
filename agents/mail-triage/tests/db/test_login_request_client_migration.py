"""U-web-settings-53: migration 0010 gives every login request the keyed digest of its client (ADR-0039)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic import command
from sqlalchemy.engine import make_url

from tests.db.conftest import alembic_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

GRANTS = Path(__file__).resolve().parents[2] / "app" / "db" / "grants.sql"
WEB_ROLE = "web_settings_runtime"
WEB_PASSWORD = "web-test-only"  # noqa: S105  # a throwaway role in a throwaway container
AGENT_ROLE = "mail_triage_runtime"
AGENT_PASSWORD = "agent-test-only"  # noqa: S105  # a throwaway role in a throwaway container
NO_CLIENT = "0" * 64

_ROW = (
    "insert into web_auth.login_request (id, username_key, code_hash, expires_at, created_at) "
    "values ('{id}', '{key}', '{key}', now() + interval '10 minutes', now())"
)
_NEW_ROW = (
    "insert into web_auth.login_request (id, username_key, client_hash, code_hash, expires_at, created_at) "
    "values ('{id}', '{key}', '{client}', '{key}', now() + interval '10 minutes', now())"
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
"""  # noqa: S608 - fixed test literals


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


async def _columns(url: str) -> dict[str, asyncpg.Record]:
    rows = await _fetch(
        url,
        "select column_name, data_type, character_maximum_length, is_nullable, column_default "
        "from information_schema.columns where table_schema = 'web_auth' and table_name = 'login_request'",
    )
    return {r["column_name"]: r for r in rows}


@pytest.fixture
async def owner(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """The owner connection with the roles made and grants.sql applied, as the migrate job does."""
    connection = await asyncpg.connect(_plain(migrated_url))
    await connection.execute(_CREATE_ROLES)
    await connection.execute(GRANTS.read_text(encoding="utf-8"))
    yield connection
    await connection.close()


async def _as(url: str, role: str, password: str) -> asyncpg.Connection:
    parts = make_url(url)
    return await asyncpg.connect(
        host=parts.host, port=parts.port, user=role, password=password, database=parts.database
    )


# Criterion 6
async def test_given_0010_when_run_up_down_and_up_then_the_column_comes_and_goes_and_old_rows_get_the_no_client_value(
    database_url: str,
) -> None:
    await _migrate(database_url, "0009")
    assert "client_hash" not in await _columns(database_url)
    await _execute(database_url, _ROW.format(id="old", key="a" * 64))

    await _migrate(database_url, "0010")

    column = (await _columns(database_url))["client_hash"]
    assert (column["data_type"], column["character_maximum_length"], column["is_nullable"]) == ("character", 64, "NO")
    assert column["column_default"] is None  # a new row must say where it came from
    rows = await _fetch(database_url, "select id, client_hash from web_auth.login_request")
    assert [(r["id"], r["client_hash"]) for r in rows] == [("old", NO_CLIENT)]

    await _downgrade(database_url, "0009")

    assert "client_hash" not in await _columns(database_url)
    assert len(await _fetch(database_url, "select 1 from web_auth.login_request")) == 1

    await _migrate(database_url, "0010")

    assert "client_hash" in await _columns(database_url)
    assert len(await _fetch(database_url, "select 1 from web_auth.login_request")) == 1


# Criterion 6
async def test_given_0010_when_a_row_has_no_client_hash_then_the_insert_is_refused(migrated_url: str) -> None:
    with pytest.raises(asyncpg.NotNullViolationError):
        await _execute(migrated_url, _ROW.format(id="x", key="b" * 64))


# Criterion 6
async def test_given_the_grants_when_the_web_role_uses_the_column_then_it_may_read_and_insert_it_but_not_change_it(
    owner: asyncpg.Connection, migrated_url: str
) -> None:
    web = await _as(migrated_url, WEB_ROLE, WEB_PASSWORD)
    try:
        await web.execute(_NEW_ROW.format(id="n", key="c" * 64, client="d" * 64))
        assert await web.fetchval("select client_hash from web_auth.login_request where id = 'n'") == "d" * 64
        await web.execute("update web_auth.login_request set dead_at = now(), attempts = 1, sent_at = now()")
        await web.execute("delete from web_auth.login_request")
        await web.execute(_NEW_ROW.format(id="m", key="c" * 64, client="d" * 64))
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await web.execute("update web_auth.login_request set client_hash = repeat('e', 64)")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await web.execute("update web_auth.login_request set username_key = repeat('e', 64)")
    finally:
        await web.close()


# Criterion 6
async def test_given_the_grants_when_the_agent_role_reads_the_column_then_it_is_refused(
    owner: asyncpg.Connection, migrated_url: str
) -> None:
    agent = await _as(migrated_url, AGENT_ROLE, AGENT_PASSWORD)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await agent.fetch("select client_hash from web_auth.login_request")
    finally:
        await agent.close()
