"""U-web-settings-71: migration 0013 (column-level INSERT, GENERATED ALWAYS id, BEFORE INSERT trigger; RT3-05, SEC3-04).

The rule for ``window``, stated once: the web app computes it from its own clock, so the trigger does not force it but
accepts it only within one window of the server's minute (``floor(epoch / 60)`` of ``now()``); anything else is 42501.
``at`` and ``count`` are always the server's. The table owner (migrations, the purge, test seeding) is not held to this.
"""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
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
CLIENT = "c" * 64
_CREATE_ROLES = f"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{WEB_ROLE}') THEN
        CREATE ROLE {WEB_ROLE} LOGIN PASSWORD 'web-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mail_triage_runtime') THEN
        CREATE ROLE mail_triage_runtime LOGIN PASSWORD 'agent-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$
"""
_SERVER_WINDOW = "floor(extract(epoch from now()) / 60)::bigint"
_TRIGGERS = "select tgname from pg_trigger where tgrelid = 'web_auth.security_event'::regclass and not tgisinternal"
_IDENTITY = (
    "select attidentity::text from pg_attribute "
    "where attrelid = 'web_auth.security_event'::regclass and attname = 'id'"
)
_FUNCTIONS = "select proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'web_auth'"
_BASE_COLUMNS = 'kind, result, request_id, client_key, "window"'
_ONCE = "on conflict on constraint uq_security_event_kind_client_window"


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _insert(columns: str, values: str) -> str:
    return f"insert into web_auth.security_event ({columns}) values ({values})"


def _normal(window: str = _SERVER_WINDOW, kind: str = "code_refused") -> str:
    return _insert(_BASE_COLUMNS, f"'{kind}', 'refused', 'req-1', '{CLIENT}', {window}")


async def _scalar(url: str, sql: str) -> object:
    connection = await asyncpg.connect(_plain(url))
    try:
        return await connection.fetchval(sql)
    finally:
        await connection.close()


async def _names(url: str, sql: str) -> list[str]:
    connection = await asyncpg.connect(_plain(url))
    try:
        return [r[0] for r in await connection.fetch(sql)]
    finally:
        await connection.close()


async def _up(url: str, revision: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), revision)


async def _down(url: str, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(url), revision)


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


# Criterion 1
@pytest.mark.parametrize(
    ("extra_column", "extra_value"),
    [
        ("at", "now() - interval '400 days'"),
        ("at", "now() + interval '400 days'"),
        ("count", "1"),
        ("count", "9999"),
    ],
)
async def test_given_the_web_role_when_it_inserts_an_explicit_at_or_count_then_it_is_refused_with_42501(
    owner: asyncpg.Connection, extra_column: str, extra_value: str
) -> None:
    async with _as(owner, WEB_ROLE) as web:
        with pytest.raises(asyncpg.PostgresError) as refused:
            await web.execute(
                _insert(
                    f"{_BASE_COLUMNS}, {extra_column}",
                    f"'code_refused', 'refused', 'req-1', '{CLIENT}', {_SERVER_WINDOW}, {extra_value}",
                )
            )
        assert refused.value.sqlstate == "42501"
    assert await owner.fetchval("select count(*) from web_auth.security_event") == 0


async def test_given_the_web_role_when_it_inserts_an_explicit_id_then_it_is_refused(owner: asyncpg.Connection) -> None:
    async with _as(owner, WEB_ROLE) as web:
        with pytest.raises(asyncpg.PostgresError) as refused:
            await web.execute(
                _insert(f"id, {_BASE_COLUMNS}", f"9000000000000000000, 'code_refused', 'refused', 'r', '{CLIENT}', 1")
            )
        assert refused.value.sqlstate in {"42501", "428C9"}  # no column grant; GENERATED ALWAYS refuses a value too
    assert await owner.fetchval("select count(*) from web_auth.security_event") == 0


async def test_given_the_web_role_when_it_inserts_normally_then_the_row_has_the_servers_at_count_and_window(
    owner: asyncpg.Connection,
) -> None:
    async with _as(owner, WEB_ROLE) as web:
        await web.execute(_normal())

    row = await owner.fetchrow(
        f'select abs(extract(epoch from now() - at)) < 5 as fresh, count, "window" = {_SERVER_WINDOW} as current '
        "from web_auth.security_event"
    )
    assert row is not None
    assert (row["fresh"], row["count"], row["current"]) == (True, 1, True)


async def test_given_a_counted_event_when_the_web_role_upserts_it_again_then_the_count_rises_by_one(
    owner: asyncpg.Connection,
) -> None:
    upsert = f"{_normal()} {_ONCE} do update set count = web_auth.security_event.count + 1"
    async with _as(owner, WEB_ROLE) as web:
        for _ in range(3):
            await web.execute(upsert)
        assert await web.fetchval("select count from web_auth.security_event") == 3
        assert await web.fetchval("select count(*) from web_auth.security_event") == 1


async def test_given_a_repeat_when_the_web_role_uses_do_nothing_then_it_stays_one_row_with_count_one(
    owner: asyncpg.Connection,
) -> None:
    drop = f"{_normal(kind='rate_limited')} {_ONCE} do nothing"
    async with _as(owner, WEB_ROLE) as web:
        await web.execute(drop)
        await web.execute(drop)
        assert await web.fetchval("select count from web_auth.security_event") == 1
        assert await web.fetchval("select count(*) from web_auth.security_event") == 1


@pytest.mark.parametrize("offset", [-1, 0, 1])
async def test_given_a_window_within_one_of_the_servers_minute_when_the_web_role_inserts_then_it_works(
    owner: asyncpg.Connection, offset: int
) -> None:
    async with _as(owner, WEB_ROLE) as web:
        await web.execute(_normal(window=f"{_SERVER_WINDOW} + ({offset})"))
        assert await web.fetchval("select count(*) from web_auth.security_event") == 1


@pytest.mark.parametrize("window", ["1", "0", "-5", f"{_SERVER_WINDOW} - 3", f"{_SERVER_WINDOW} + 3", "9000000000"])
async def test_given_a_window_far_from_the_servers_minute_when_the_web_role_inserts_then_it_is_refused_with_42501(
    owner: asyncpg.Connection, window: str
) -> None:
    async with _as(owner, WEB_ROLE) as web:
        with pytest.raises(asyncpg.PostgresError) as refused:
            await web.execute(_normal(window=window))
        assert refused.value.sqlstate == "42501"


async def test_given_the_web_role_when_privileges_are_read_then_only_six_columns_are_insertable(
    owner: asyncpg.Connection,
) -> None:
    rows = await owner.fetch(
        "select column_name from information_schema.columns where table_schema = 'web_auth' "
        "and table_name = 'security_event' "
        "and has_column_privilege($1, 'web_auth.security_event', column_name, 'INSERT')",
        WEB_ROLE,
    )
    nextval = await owner.fetchval(
        "select has_sequence_privilege($1, 'web_auth.security_event_id_seq', 'USAGE')", WEB_ROLE
    )

    assert {r["column_name"] for r in rows} == {
        "kind",
        "result",
        "username_hash",
        "request_id",
        "client_key",
        "window",
    }
    assert nextval is False  # the sequence cannot be advanced by hand either


async def test_given_the_owner_when_it_seeds_an_event_with_an_explicit_at_and_count_then_it_is_kept(
    owner: asyncpg.Connection,
) -> None:
    await owner.execute(
        _insert(f"at, count, {_BASE_COLUMNS}", "now() - interval '100 days', 4, 'code_refused', 'refused', 'r', 'k', 7")
    )

    row = await owner.fetchrow(
        "select now() - at > interval '99 days' as old, count, \"window\" from web_auth.security_event"
    )
    assert row is not None
    assert (row["old"], row["count"], row["window"]) == (True, 4, 7)


async def test_given_0013_when_the_id_is_inspected_then_it_is_generated_always(owner: asyncpg.Connection) -> None:
    assert await owner.fetchval(_IDENTITY) == "a"
    with pytest.raises(asyncpg.PostgresError) as refused:
        await owner.execute(_insert(f"id, {_BASE_COLUMNS}", "5, 'code_refused', 'refused', 'r', 'k', 7"))
    assert refused.value.sqlstate == "428C9"


# Criterion 3
async def test_given_0013_when_run_up_down_and_up_then_identity_trigger_and_function_come_and_go(
    database_url: str,
) -> None:
    await _up(database_url, "0012")
    before = await _names(database_url, _TRIGGERS)
    assert await _scalar(database_url, _IDENTITY) == "d"

    await _up(database_url, "0013")

    assert await _scalar(database_url, _IDENTITY) == "a"
    assert len(await _names(database_url, _TRIGGERS)) == len(before) + 1
    assert "security_event_insert_guard" in await _names(database_url, _FUNCTIONS)

    await _down(database_url, "0012")

    assert await _scalar(database_url, _IDENTITY) == "d"
    assert await _names(database_url, _TRIGGERS) == before
    assert "security_event_insert_guard" not in await _names(database_url, _FUNCTIONS)

    await _up(database_url, "0013")

    assert await _scalar(database_url, _IDENTITY) == "a"
    assert len(await _names(database_url, _TRIGGERS)) == len(before) + 1


async def test_given_rows_when_0013_runs_down_and_up_then_the_rows_and_the_id_sequence_survive(
    database_url: str,
) -> None:
    await _up(database_url, "0013")
    connection = await asyncpg.connect(_plain(database_url))
    try:
        await connection.execute(_normal())
        await _down(database_url, "0012")
        await connection.execute(_normal(kind="rate_limited"))
        await _up(database_url, "0013")
        await connection.execute(_normal(kind="csrf_refused"))
        ids = [r["id"] for r in await connection.fetch("select id from web_auth.security_event order by id")]
    finally:
        await connection.close()

    assert ids == sorted(set(ids))
    assert len(ids) == 3
