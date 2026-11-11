"""U-web-settings-09, database level: readiness, start-up purge, statement timeout, clean state per test."""

from collections.abc import AsyncIterator
from datetime import timedelta

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import Database
from app.startup import attach_database
from tests.db.conftest import DbEndpoint
from tests.fakes import FakeClock, make_app

A64 = "a" * 64


@pytest.fixture
async def ready_client(web_database: Database) -> AsyncIterator[AsyncClient]:
    app = make_app()
    attach_database(app, web_database, FakeClock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def test_given_a_migrated_database_when_readyz_then_200(ready_client: AsyncClient) -> None:
    response = await ready_client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_given_another_contract_version_when_readyz_then_503_with_a_generic_body(
    ready_client: AsyncClient, owner: asyncpg.Connection
) -> None:
    await owner.execute(
        "CREATE OR REPLACE FUNCTION settings.contract_version() RETURNS integer "
        "LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$ SELECT 2 $$"
    )

    response = await ready_client.get("/readyz")

    assert response.status_code == 503
    assert "contract" not in response.text.lower()
    assert "2" not in response.text


async def test_given_the_web_role_when_it_calls_the_contract_version_then_it_is_allowed_but_owns_nothing(
    web_database: Database,
) -> None:
    async with web_database.session() as session:
        assert (await session.execute(text("select settings.contract_version()"))).scalar_one() == 1
        with pytest.raises(Exception, match="permission denied"):
            await session.execute(text("select count(*) from settings.settings_change"))


async def test_given_expired_and_valid_rows_when_the_app_starts_then_only_the_expired_rows_are_removed(
    web_database: Database, owner: asyncpg.Connection
) -> None:
    clock = FakeClock()
    now = clock.now()
    login = (
        "insert into web_auth.login_request (id, username_key, code_hash, expires_at, created_at) "
        "values ($1, $2, $2, $3, $4)"
    )
    # Old and expired: gone. Expired a little ago: kept an hour so the hourly cap can still count it. Open: kept.
    await owner.execute(login, "old", A64, now - timedelta(hours=2) + timedelta(minutes=10), now - timedelta(hours=2))
    await owner.execute(login, "recent", A64, now - timedelta(minutes=20), now - timedelta(minutes=30))
    await owner.execute(login, "open", A64, now + timedelta(minutes=9), now - timedelta(minutes=1))
    session = (
        "insert into web_auth.session (id_hash, username_hash, last_seen_at, absolute_expires_at) "
        "values ($1, $2, $3, $4)"
    )
    await owner.execute(session, "1" * 64, A64, now - timedelta(minutes=1), now - timedelta(minutes=1))
    await owner.execute(session, "2" * 64, A64, now - timedelta(minutes=31), now + timedelta(hours=5))
    await owner.execute(session, "3" * 64, A64, now - timedelta(minutes=5), now + timedelta(hours=5))
    app = make_app()
    attach_database(app, web_database, clock)

    async with app.router.lifespan_context(app):
        pass

    assert {r["id"] for r in await owner.fetch("select id from web_auth.login_request")} == {"recent", "open"}
    assert {r["id_hash"] for r in await owner.fetch("select id_hash from web_auth.session")} == {"3" * 64}


async def test_given_a_statement_slower_than_the_timeout_when_run_then_it_is_cancelled_and_the_request_ends_503(
    db: DbEndpoint,
) -> None:
    database = Database.create(db.web_url, ssl_context=None, statement_timeout_ms=200)
    app = FastAPI()
    attach_database(app, database, FakeClock())

    @app.get("/slow")
    async def slow() -> dict[str, int]:
        async with database.session() as session:
            await session.execute(text("select pg_sleep(5)"))
        return {}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/slow")
    finally:
        await database.dispose()

    assert response.status_code == 503
    assert "57014" not in response.text
    assert "pg_sleep" not in response.text


async def test_given_a_first_test_that_writes_when_it_ends_then_the_data_is_its_own(
    owner: asyncpg.Connection,
) -> None:
    await owner.execute(
        "insert into web_auth.web_lock (id, locked_at) values (1, now())",
    )
    await owner.execute("create table public.leftover (id int)")

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1


async def test_given_a_second_test_after_it_when_it_starts_then_the_schema_state_is_clean(
    owner: asyncpg.Connection,
) -> None:
    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 0
    assert await owner.fetchval("select to_regclass('public.leftover')") is None
