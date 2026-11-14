"""U-web-settings-60, database level: expired rows are purged on the first request of each hour (injected clock)."""

import logging
from datetime import timedelta

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import startup
from app.db import Database
from app.startup import attach_database
from tests.fakes import FakeClock, make_app

A64 = "a" * 64
HEALTH = "/healthz"


async def _seed_expired(owner: asyncpg.Connection, clock: FakeClock, tag: str) -> None:
    now = clock.now()
    await owner.execute(
        "insert into web_auth.login_request (id, username_key, client_hash, code_hash, expires_at, created_at) "
        "values ($1, $2, $2, $2, $3, $4)",
        f"old-{tag}",
        A64,
        now - timedelta(hours=2) + timedelta(minutes=10),
        now - timedelta(hours=2),
    )
    await owner.execute(
        "insert into web_auth.session (id_hash, username_hash, last_seen_at, absolute_expires_at) "
        "values ($1, $2, $3, $4)",
        tag * 64,
        A64,
        now - timedelta(minutes=1),
        now - timedelta(minutes=1),
    )


async def _remaining(owner: asyncpg.Connection) -> tuple[int, int]:
    logins = await owner.fetchval("select count(*) from web_auth.login_request")
    sessions = await owner.fetchval("select count(*) from web_auth.session")
    return logins, sessions


async def test_given_expired_rows_when_an_hour_passes_then_the_next_request_purges_them_once(
    web_database: Database, owner: asyncpg.Connection
) -> None:
    clock = FakeClock()
    app = make_app()
    attach_database(app, web_database, clock)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await _seed_expired(owner, clock, "1")

        clock.advance(timedelta(minutes=59))
        await client.get(HEALTH)
        assert await _remaining(owner) == (1, 1)

        clock.advance(timedelta(minutes=1))
        await client.get(HEALTH)
        assert await _remaining(owner) == (0, 0)

        await _seed_expired(owner, clock, "2")
        clock.advance(timedelta(minutes=30))
        await client.get(HEALTH)
        assert await _remaining(owner) == (1, 1)

        clock.advance(timedelta(minutes=30))
        await client.get(HEALTH)
        assert await _remaining(owner) == (0, 0)


async def test_given_a_failing_purge_when_a_request_arrives_then_it_is_answered_and_the_log_has_no_detail(
    web_database: Database, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    app = make_app()
    attach_database(app, web_database, clock)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):

        async def failing(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("secret-detail-canary")

        monkeypatch.setattr(startup, "purge_expired", failing)
        clock.advance(timedelta(hours=1))
        with caplog.at_level(logging.WARNING):
            response = await client.get(HEALTH)

    assert response.status_code == 200
    assert any(r.getMessage() == "purge.failed" for r in caplog.records)
    assert "secret-detail-canary" not in caplog.text
