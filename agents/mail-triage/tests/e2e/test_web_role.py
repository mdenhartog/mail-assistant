"""U-web-settings-42 (AC-17, W-8): what the web role can and cannot do in the running prod-like stack.

Run by the `prod-like` CI job after the migrate service and ``docker compose --profile prod-like up -d --build --wait``,
from the repository root:

    E2E_PROD_LIKE=1 uv run --frozen --project agents/mail-triage pytest --no-cov agents/mail-triage/tests/e2e

The role connects like the api does: to the host name ``db`` (the job adds it to /etc/hosts; the certificate carries
that name only) over TLS, checked against the private CA of ``deploy/prod-like/certs.sh``. It needs
``WEB_ROLE_PASSWORD`` in the environment; no password is written in this file. Everything that works is done in a
transaction that is rolled back, so a stack that already holds settings is left as it was.
"""

# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway stack, never user input

from __future__ import annotations

import os
import ssl
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_PROD_LIKE"), reason="needs the running prod-like stack")

ROOT = Path(__file__).resolve().parents[4]
CA = ROOT / "deploy" / "prod-like" / "certs" / "ca.crt"
WEB_ROLE = "web_settings_runtime"
INSUFFICIENT_PRIVILEGE = "42501"
ACTOR = "web:" + "ab" * 16
_FIRST_ROW = (  # fixed test literals, no input
    "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, version, "
    f"updated_via, updated_by) values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 1, 'web', '{ACTOR}')"
)


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        pytest.fail(f"{name} must be set to the value the stack was started with")  # a gate: fail, never skip
    return value


@pytest.fixture
async def web() -> AsyncIterator[asyncpg.Connection]:
    context = ssl.create_default_context(cafile=str(CA))
    connection = await asyncpg.connect(
        host="db",
        port=int(os.environ.get("DB_PORT", "5432")),
        user=WEB_ROLE,
        password=_require("WEB_ROLE_PASSWORD"),
        database="app",
        ssl=context,
        timeout=15,
    )
    yield connection
    await connection.close()


async def _sqlstate(connection: asyncpg.Connection, statement: str) -> str | None:
    """Run ``statement`` in a transaction that is rolled back; the SQLSTATE of its refusal, or None when it ran."""
    transaction = connection.transaction()
    await transaction.start()
    try:
        await connection.execute(statement)
    except asyncpg.PostgresError as error:
        return error.sqlstate
    finally:
        await transaction.rollback()
    return None


@pytest.mark.parametrize(
    "statement",
    [
        "select * from public.mail_item",
        "select * from public.oauth_token",
        "select * from public.alert",
        "select * from public.draft",
        "select * from public.audit_log",
        "select * from settings.settings_change",
        "insert into settings.settings_change (via, by, new) values ('web', 'x', '{}')",
        "delete from settings.settings_change",
        "truncate settings.settings_change",
    ],
)
async def test_given_the_web_role_when_it_reads_mail_tokens_or_the_audit_then_postgres_refuses_it(
    web: asyncpg.Connection, statement: str
) -> None:
    assert await _sqlstate(web, statement) == INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize(
    "statement",
    [
        "create table public.evil (id int)",
        "create table settings.evil (id int)",
        "create table web_auth.evil (id int)",
        "create schema evil",
        "alter table settings.schedule add column evil text",
        "drop table settings.schedule",
        "drop table web_auth.session",
        "alter table settings.schedule disable trigger schedule_audit",
        "create role evil login",
        "set session_replication_role = replica",
    ],
)
async def test_given_the_web_role_when_it_runs_ddl_or_tries_to_get_around_a_trigger_then_postgres_refuses_it(
    web: asyncpg.Connection, statement: str
) -> None:
    assert await _sqlstate(web, statement) == INSUFFICIENT_PRIVILEGE


async def _ensure_row(web: asyncpg.Connection) -> int:
    """The version of the stored schedule; the first row is created when the stack has none yet."""
    if not await web.fetchval("select count(*) from settings.schedule"):
        await web.execute(_FIRST_ROW)
    return int(await web.fetchval("select version from settings.schedule"))


@pytest.mark.parametrize(
    "change",
    [
        "version = version + 1, updated_via = 'web', updated_by = 'someone'",  # not web:<32 hex>
        "version = version + 1, updated_via = 'web', updated_by = 'telegram'",
        "version = version + 1, updated_via = 'telegram', updated_by = '{actor}'",  # the other role's channel
        "version = version + 2, updated_via = 'web', updated_by = '{actor}'",  # must rise by exactly one
        "version = version, updated_via = 'web', updated_by = '{actor}'",
    ],
)
async def test_given_a_stored_schedule_when_the_web_role_writes_a_bad_actor_channel_or_version_then_it_is_refused(
    web: asyncpg.Connection, change: str
) -> None:
    transaction = web.transaction()
    await transaction.start()
    try:
        await _ensure_row(web)
        refused = None
        try:
            await web.execute(f"update settings.schedule set {change.format(actor=ACTOR)}")
        except asyncpg.PostgresError as error:
            refused = error.sqlstate
    finally:
        await transaction.rollback()

    assert refused == INSUFFICIENT_PRIVILEGE, f"{change!r} was not refused with 42501"


async def test_given_the_web_role_when_it_saves_a_valid_change_then_it_works(web: asyncpg.Connection) -> None:
    transaction = web.transaction()
    await transaction.start()
    try:
        version = await _ensure_row(web)
        await web.execute(
            "update settings.schedule set quiet_start = 660, "
            f"version = {version + 1}, updated_via = 'web', updated_by = '{ACTOR}'"
        )
        stored = await web.fetchval("select quiet_start from settings.schedule")
        contract = await web.fetchval("select settings.contract_version()")
    finally:
        await transaction.rollback()

    assert stored == 660
    assert contract == 2


async def test_given_the_web_role_when_its_attributes_are_read_then_it_is_a_plain_login_role_over_tls(
    web: asyncpg.Connection,
) -> None:
    row = await web.fetchrow(
        "select r.rolsuper, r.rolcreaterole, r.rolcreatedb, r.rolreplication, r.rolbypassrls, s.ssl "
        "from pg_roles r, pg_stat_ssl s where r.rolname = current_user and s.pid = pg_backend_pid()"
    )

    assert row is not None
    assert dict(row) == {
        "rolsuper": False,
        "rolcreaterole": False,
        "rolcreatedb": False,
        "rolreplication": False,
        "rolbypassrls": False,
        "ssl": True,
    }
