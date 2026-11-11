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
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_settings_runtime') THEN
        CREATE ROLE web_settings_runtime LOGIN PASSWORD 'web-test-password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;  -- grants.sql names the web role too (U-web-settings-08 removed its guard)
END $$
"""


def _schedule(via: str) -> str:
    return (  # fixed test literals, no input
        "insert into settings.schedule "  # noqa: S608
        "(id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, updated_by) "
        f"values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, '{via}', 'u1')"
    )


# The owner seeds the row; its session_user is not a mapped role, so the channel it claims is kept.
_SCHEDULE = _schedule("web")
_TELEGRAM_UPDATE = "update settings.schedule set quiet_start = 660, version = 2, updated_via = 'telegram'"


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
        # Least privilege per table (ADR-0030 item 1): append-only audit trail, deletes only on the dialogue.
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
        "truncate audit_log",
        "truncate mail_item cascade",
        # The version rises by exactly one (ADR-0030 item 2).
        "update settings.schedule set quiet_start = 660, version = 1, updated_via = 'telegram'",
        "update settings.schedule set quiet_start = 660, version = 3, updated_via = 'telegram'",
        "update settings.schedule set quiet_start = 660, version = 0, updated_via = 'telegram'",
        # The channel is the role's, not the writer's choice.
        "update settings.schedule set quiet_start = 660, version = 2, updated_via = 'web'",
        "update settings.schedule set quiet_start = 660, version = 2",
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
    await runtime.execute(_schedule("telegram"))
    await runtime.execute(_TELEGRAM_UPDATE)

    assert await runtime.fetchval("select quiet_start from settings.schedule") == 660
    assert await owner.fetchval("select count(*) from settings.settings_change") == 2


async def test_given_the_runtime_role_when_it_inserts_the_first_row_as_web_then_postgres_refuses_it(
    runtime: asyncpg.Connection,
) -> None:
    with pytest.raises(asyncpg.PostgresError) as refused:
        await runtime.execute(_schedule("web"))

    assert refused.value.sqlstate == "42501"


async def test_given_the_runtime_role_when_it_inserts_a_first_row_above_version_one_then_postgres_refuses_it(
    runtime: asyncpg.Connection,
) -> None:
    statement = _schedule("telegram").replace("updated_by)", "updated_by, version)").replace("'u1')", "'u1', 7)")

    with pytest.raises(asyncpg.PostgresError) as refused:
        await runtime.execute(statement)

    assert refused.value.sqlstate == "42501"


async def test_given_a_telegram_write_when_it_is_recorded_then_the_server_stores_the_session_user_and_the_time(
    runtime: asyncpg.Connection, owner: asyncpg.Connection
) -> None:
    await runtime.execute(_schedule("telegram"))
    stamp = await owner.fetchval("select updated_at from settings.schedule")
    await runtime.execute(
        "update settings.schedule set quiet_start = 660, version = 2, updated_via = 'telegram', "
        "updated_at = '2001-01-01 00:00:00+00'"
    )

    row = await owner.fetchrow("select updated_at from settings.schedule")
    records = await owner.fetch("select via, db_role from settings.settings_change order by new -> 'version'")

    assert row is not None
    assert row["updated_at"] > stamp  # the client's updated_at is overwritten by the server
    assert [(r["via"], r["db_role"]) for r in records] == [("telegram", ROLE), ("telegram", ROLE)]


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
    await runtime.execute("update mail_item set urgent = false")
    await runtime.execute("update alert set state = 'sent'")
    await runtime.execute("insert into audit_log (kind, ref, at) values ('k', 'r', now())")
    await runtime.execute("insert into overview_log (day, settled_at) values (current_date, now())")
    await runtime.execute("insert into oauth_token (id, ciphertext, updated_at) values (1, 'x', now())")
    await runtime.execute("update oauth_token set updated_at = now()")
    await runtime.execute("insert into poll_state (id, history_id) values (1, '1')")
    await runtime.execute("update poll_state set history_id = '2'")
    await runtime.execute("update poll_state set telegram_update_id = 5000000000")
    await runtime.execute("insert into catchup_state (id, started_at) values (1, now())")
    await runtime.execute("update catchup_state set finished_at = now()")

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
