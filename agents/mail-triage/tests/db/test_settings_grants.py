"""U-quiet-hours-04: the runtime role, created from app/db/grants.sql, is limited as ADR-0025 demands (AC-30)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

GRANTS = Path(__file__).resolve().parents[2] / "app" / "db" / "grants.sql"
ROLE = "mail_triage_runtime"
PASSWORD = "runtime-test-only"  # noqa: S105  # a throwaway role inside a throwaway test container

_CREATE_ROLE = f"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN
        CREATE ROLE {ROLE} LOGIN PASSWORD '{PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$
"""

_SCHEDULE = (
    "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, updated_by) "
    "values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', 'u1')"
)


@pytest.fixture
async def owner(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection as the owner (the test container's superuser, who ran the migrations) with the grants applied."""
    connection = await asyncpg.connect(migrated_url.replace("postgresql+asyncpg://", "postgresql://"))
    await connection.execute(_CREATE_ROLE)
    await connection.execute(GRANTS.read_text(encoding="utf-8"))
    yield connection
    await connection.close()


@pytest.fixture
async def runtime(owner: asyncpg.Connection, migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection as the runtime role."""
    url = make_url(migrated_url)
    connection = await asyncpg.connect(
        host=url.host, port=url.port, user=ROLE, password=PASSWORD, database=url.database
    )
    yield connection
    await connection.close()


@pytest.mark.parametrize(
    "statement",
    [
        "update settings.settings_change set via = 'web'",
        "delete from settings.settings_change",
        "truncate settings.settings_change",
        "insert into settings.settings_change (via, by, new) values ('web', 'x', '{}')",
        "delete from settings.schedule",
        "truncate settings.schedule",
        "create table public.evil (id int)",
        "create schema evil",
        "create table settings.evil (id int)",
        "alter table settings.schedule drop constraint ck_schedule_single_row",
        "alter table alert add column evil text",
        "drop table alert",
        "drop trigger schedule_audit on settings.schedule",
        "alter table settings.schedule disable trigger schedule_audit",
        "set session_replication_role = replica",
        "set role test",
    ],
)
async def test_given_the_runtime_role_when_it_tries_a_forbidden_statement_then_postgres_refuses_it(
    runtime: asyncpg.Connection, owner: asyncpg.Connection, statement: str
) -> None:
    await owner.execute(_SCHEDULE)

    with pytest.raises(asyncpg.PostgresError) as refused:
        await runtime.execute(statement)

    assert refused.value.sqlstate == "42501"


async def test_given_the_runtime_role_when_it_inserts_and_updates_the_schedule_then_the_trigger_records_it(
    runtime: asyncpg.Connection, owner: asyncpg.Connection
) -> None:
    await runtime.execute(_SCHEDULE)
    await runtime.execute("update settings.schedule set quiet_start = 660, version = 2, updated_via = 'telegram'")

    assert await runtime.fetchval("select quiet_start from settings.schedule") == 660
    assert await owner.fetchval("select count(*) from settings.settings_change") == 2


async def test_given_the_runtime_role_when_it_works_on_mail_and_conversation_then_it_may(
    runtime: asyncpg.Connection,
) -> None:
    await runtime.execute(
        "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) values ('m1', 't1', true, now())"
    )
    await runtime.execute(
        "insert into alert (mail_item_id, state, release_at, created_at, updated_at) "
        "select id, 'held', now(), now(), now() from mail_item"
    )
    await runtime.execute(
        "insert into conversation (id, kind, step, nonce, expires_at) values (1, 'settings', 's', 'n', now())"
    )
    await runtime.execute("delete from conversation")

    assert await runtime.fetchval("select count(*) from alert") == 1


async def test_given_the_runtime_role_when_ownership_is_listed_then_it_owns_nothing(
    runtime: asyncpg.Connection,
) -> None:
    owned = await runtime.fetch(
        "select c.relname from pg_class c join pg_roles r on r.oid = c.relowner where r.rolname = $1", ROLE
    )
    functions = await runtime.fetch(
        "select p.proname from pg_proc p join pg_roles r on r.oid = p.proowner where r.rolname = $1", ROLE
    )

    assert owned == []
    assert functions == []
