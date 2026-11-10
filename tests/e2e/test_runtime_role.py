"""U-quiet-hours-15b (AC-30): what the mail-triage runtime role can and cannot do in the running prod-like stack.

Start the stack first (``docker compose --profile prod-like up -d --build --wait``, with POSTGRES_PASSWORD and
MAIL_TRIAGE_RUNTIME_PASSWORD in the environment or in .env), then run, from the repository root:

    uv run --project agents/mail-triage pytest -c tests/e2e/pytest.ini tests/e2e

The checks connect to the published database port as the role ``mail_triage_runtime``, with the password the migrate
job gave it. Everything that works is done inside a transaction that is rolled back, so a stack that already holds real
settings is left as it was. Values come from the environment; no password is written in this file.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import asyncpg
import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

ROLE = "mail_triage_runtime"
INSUFFICIENT_PRIVILEGE = "42501"


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        pytest.fail(f"{name} must be set to the value the stack was started with")  # fail, never skip: this is a gate
    return value


async def _connect(user: str, password: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=os.environ.get("E2E_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=user,
        password=password,
        database="app",
        timeout=15,
    )


@pytest.fixture
async def runtime() -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect(ROLE, _require("MAIL_TRIAGE_RUNTIME_PASSWORD"))
    yield connection
    await connection.close()


FORBIDDEN = [
    # DDL
    "create table public.evil (id int)",
    "create table settings.evil (id int)",
    "create schema evil",
    "alter table settings.schedule add column evil text",
    "alter table public.alert add column evil text",
    "drop table public.alert",
    "drop table settings.settings_change",
    "drop schema settings cascade",
    "drop trigger schedule_audit on settings.schedule",
    "alter table settings.schedule disable trigger schedule_audit",
    # The audit rows
    "delete from settings.settings_change",
    "update settings.settings_change set via = 'web'",
    "truncate settings.settings_change",
    "truncate settings.schedule cascade",
    "insert into settings.settings_change (via, by, new) values ('web', 'x', '{}')",
    # Least privilege per table (ADR-0030): append-only audit, no deletes outside the dialogue
    "update audit_log set kind = 'x'",
    "delete from audit_log",
    "delete from oauth_token",
    "delete from mail_item",
    "delete from alert",
    "delete from draft",
    "delete from poll_state",
    "delete from catchup_state",
    "delete from overview_log",
    "update overview_log set settled_at = now()",
    # Privilege escalation
    "create role evil login",
    "alter role mail_triage_runtime superuser",
    "alter role mail_triage_runtime createrole",
    "set session_replication_role = replica",
]


@pytest.mark.parametrize("statement", FORBIDDEN)
async def test_given_the_runtime_role_when_it_runs_a_forbidden_statement_then_postgres_refuses_it(
    runtime: asyncpg.Connection, statement: str
) -> None:
    with pytest.raises(asyncpg.PostgresError) as refused:
        await runtime.execute(statement)

    assert refused.value.sqlstate == INSUFFICIENT_PRIVILEGE, f"{statement!r} was not refused with 42501"


async def test_given_the_runtime_role_when_its_attributes_are_read_then_it_is_a_plain_login_role(
    runtime: asyncpg.Connection,
) -> None:
    row = await runtime.fetchrow(
        "select rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolcanlogin "
        "from pg_roles where rolname = current_user"
    )

    assert row is not None
    assert dict(row) == {
        "rolsuper": False,
        "rolcreaterole": False,
        "rolcreatedb": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "rolcanlogin": True,
    }
    assert await runtime.fetchval("select current_user") == ROLE


async def test_given_the_runtime_role_when_ownership_is_listed_then_it_owns_no_table_schema_or_function(
    runtime: asyncpg.Connection,
) -> None:
    tables = await runtime.fetch(
        "select c.relname from pg_class c join pg_roles r on r.oid = c.relowner where r.rolname = current_user"
    )
    schemas = await runtime.fetch(
        "select n.nspname from pg_namespace n join pg_roles r on r.oid = n.nspowner where r.rolname = current_user"
    )
    functions = await runtime.fetch(
        "select p.proname from pg_proc p join pg_roles r on r.oid = p.proowner where r.rolname = current_user"
    )

    assert (tables, schemas, functions) == ([], [], [])


async def test_given_the_runtime_role_when_it_writes_settings_then_the_audit_row_is_added_and_nothing_is_kept(
    runtime: asyncpg.Connection,
) -> None:
    transaction = runtime.transaction()
    await transaction.start()
    try:
        before = await runtime.fetchval("select count(*) from settings.settings_change")
        if await runtime.fetchval("select count(*) from settings.schedule"):
            await runtime.execute(
                "update settings.schedule set version = version + 1, updated_via = 'telegram', "
                "updated_by = 'e2e-role-check'"
            )
        else:
            await runtime.execute(
                "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, "
                "updated_via, updated_by) values "
                "(1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'telegram', 'e2e-role-check')"
            )
        after = await runtime.fetchval("select count(*) from settings.settings_change")
        recorded = await runtime.fetchrow(
            "select via, db_role from settings.settings_change where by = 'e2e-role-check' order by at desc limit 1"
        )
        mail = await runtime.fetchval("select count(*) from mail_item")
        revision = await runtime.fetchval("select version_num from alembic_version")
    finally:
        await transaction.rollback()

    assert after == before + 1  # the trigger wrote it; the role could not have inserted it itself
    assert recorded is not None
    assert (recorded["via"], recorded["db_role"]) == ("telegram", ROLE)  # derived by the server, not claimed
    assert mail >= 0
    assert revision  # the readiness check the agent runs at start-up works


_FORGED_WRITES = [
    "update settings.schedule set version = version + 2, updated_via = 'telegram'",
    "update settings.schedule set version = version, updated_via = 'telegram'",
    "update settings.schedule set version = version + 1, updated_via = 'web'",
]


@pytest.mark.parametrize("statement", _FORGED_WRITES)
async def test_given_a_stored_schedule_when_the_runtime_role_forges_the_channel_or_the_version_then_it_is_refused(
    runtime: asyncpg.Connection, statement: str
) -> None:
    transaction = runtime.transaction()
    await transaction.start()
    try:
        if not await runtime.fetchval("select count(*) from settings.schedule"):
            await runtime.execute(
                "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, "
                "updated_via, updated_by) values "
                "(1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'telegram', 'e2e-role-check')"
            )
        with pytest.raises(asyncpg.PostgresError) as refused:
            await runtime.execute(statement)
    finally:
        await transaction.rollback()

    assert refused.value.sqlstate == INSUFFICIENT_PRIVILEGE, f"{statement!r} was not refused with 42501"


async def test_given_the_runtime_role_when_it_works_on_mail_and_conversation_then_it_may(
    runtime: asyncpg.Connection,
) -> None:
    transaction = runtime.transaction()
    await transaction.start()
    try:
        await runtime.execute(
            "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) "
            "values ('e2e-role-check', 't', false, now())"
        )
        await runtime.execute("update mail_item set urgent = true where gmail_message_id = 'e2e-role-check'")
        urgent = await runtime.fetchval("select urgent from mail_item where gmail_message_id = 'e2e-role-check'")
        await runtime.execute(
            "insert into conversation (id, kind, step, nonce, expires_at) values (1, 'settings', 's', 'n', now())"
        )
        await runtime.execute("delete from conversation")
    finally:
        await transaction.rollback()

    assert urgent is True
