"""U-web-settings-54: migration 0011 gives every security event a count and takes the clear client address away."""

from __future__ import annotations

import asyncio
import hashlib
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
CLIENT = "203.0.113.7"

_OLD_ROW = (
    "insert into web_auth.security_event (kind, result, request_id, client_key, \"window\") "
    "values ('{kind}', 'refused', 'r-{window}', '{client}', {window})"
)
_NEW_ROW = (
    "insert into web_auth.security_event (kind, result, request_id, client_key, \"window\", count) "
    "values ('code_refused', 'refused', 'r-1', '{client}', 1, {count})"
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
        "select column_name, data_type, is_nullable, column_default "
        "from information_schema.columns where table_schema = 'web_auth' and table_name = 'security_event'",
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


# Criterion 1 and 2
async def test_given_0011_when_run_up_down_and_up_then_count_comes_and_goes_and_old_rows_lose_their_address(
    database_url: str,
) -> None:
    await _migrate(database_url, "0010")
    assert "count" not in await _columns(database_url)
    await _execute(database_url, _OLD_ROW.format(kind="code_refused", client=CLIENT, window=1))
    await _execute(database_url, _OLD_ROW.format(kind="code_refused", client=CLIENT, window=2))

    await _migrate(database_url, "0011")

    column = (await _columns(database_url))["count"]
    assert (column["data_type"], column["is_nullable"], column["column_default"]) == ("integer", "NO", "1")
    rows = await _fetch(database_url, 'select client_key, count, "window" from web_auth.security_event order by 3')
    assert [r["count"] for r in rows] == [1, 1]
    keys = [r["client_key"].strip() for r in rows]
    assert CLIENT not in keys
    assert all(len(key) == 64 and set(key) <= set("0123456789abcdef") for key in keys)
    assert keys[0] != keys[1]  # the unique constraint of (kind, client, window) still holds
    assert keys[0] != hashlib.sha256(CLIENT.encode()).hexdigest()  # not an unkeyed digest of the address

    await _downgrade(database_url, "0010")

    assert "count" not in await _columns(database_url)
    after = await _fetch(database_url, "select client_key from web_auth.security_event")
    assert len(after) == 2
    assert CLIENT not in [r["client_key"].strip() for r in after]  # a digest cannot be turned back

    await _migrate(database_url, "0011")

    assert "count" in await _columns(database_url)
    assert len(await _fetch(database_url, "select 1 from web_auth.security_event")) == 2


# Criterion 1 (least privilege)
async def test_given_the_grants_when_the_web_role_counts_then_it_may_change_count_and_nothing_else(
    owner: asyncpg.Connection, migrated_url: str
) -> None:
    web = await _as(migrated_url, WEB_ROLE, WEB_PASSWORD)
    try:
        await web.execute(_NEW_ROW.format(client="d" * 64, count=1))
        await web.execute("update web_auth.security_event set count = count + 1")
        assert await web.fetchval("select count from web_auth.security_event") == 2
        for column in ("client_key = repeat('e', 64)", "kind = 'rate_limited'", "result = 'ok'", "request_id = 'x'"):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await web.execute(f"update web_auth.security_event set {column}")  # noqa: S608 - fixed literals
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await web.execute("delete from web_auth.security_event")
    finally:
        await web.close()


async def test_given_the_grants_when_the_agent_role_reads_events_then_it_is_still_refused(
    owner: asyncpg.Connection, migrated_url: str
) -> None:
    agent = await _as(migrated_url, AGENT_ROLE, AGENT_PASSWORD)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await agent.fetch("select count from web_auth.security_event")
    finally:
        await agent.close()
