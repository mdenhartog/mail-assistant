# pyright: reportUnusedImport=false
"""U-web-settings-24: the real guard in front of the sign-in routes, with a real PostgreSQL (db level)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.auth.login_requests import LoginRequests
from app.auth.request_code import attach_request_code
from app.auth.request_code_rules import client_hash
from app.db import Database
from app.ids import SecretsIdSource
from app.main import build_app
from app.security_events import SecurityEvents
from app.startup import attach_database
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.fakes import FakeClock, FakeCodes, FakeMailer, make_settings

T0 = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)
ORIGIN = "https://settings.example.test"
CODES = [f"{n:06d}" for n in range(100000, 100200)]


@dataclass
class Api:
    http: AsyncClient
    clock: FakeClock

    async def request_code(self, username: str) -> Response:
        return await self.http.post("/auth/request-code", json={"username": username}, headers={"Origin": ORIGIN})


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    ids = SecretsIdSource()
    # The per-client limits of the login requests (ADR-0039) are tested elsewhere; here the rate limiter is the subject.
    settings = make_settings(open_login_requests_per_client=1000, login_requests_per_client_per_hour=1000)
    app = build_app(settings, clock=clock, ids=ids, codes=FakeCodes(list(CODES)), mailer=FakeMailer())
    store = LoginRequests(web_database, ids, hash_key=b"a" * 32, ttl=timedelta(seconds=600), max_attempts=5)
    attach_database(app, web_database, clock)
    attach_request_code(app, store, SecurityEvents(web_database, clock, b"e" * 32))
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.50", 5000)), base_url="http://t"
    ) as http:
        yield Api(http, clock)


async def _rows(owner: asyncpg.Connection) -> int:  # noqa: F811
    return await owner.fetchval("SELECT count(*) FROM web_auth.login_request")


async def _events(owner: asyncpg.Connection) -> list[asyncpg.Record]:  # noqa: F811
    return await owner.fetch(
        'SELECT kind, result, client_key, request_id, username_hash, "window" FROM web_auth.security_event '
        "WHERE kind = 'rate_limited' ORDER BY id"
    )


# Criterion 1
async def test_given_30_code_requests_in_one_window_when_the_31st_arrives_then_429_until_the_next_minute(
    api: Api,
) -> None:
    statuses = [(await api.request_code(f"someone-{n}")).status_code for n in range(30)]
    refused = await api.request_code("someone-30")
    api.clock.advance(timedelta(seconds=59.9))
    still = await api.request_code("someone-31")
    api.clock.advance(timedelta(seconds=0.1))
    fresh = await api.request_code("someone-32")

    assert statuses == [200] * 30
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "60"
    assert still.status_code == 429
    assert still.headers["retry-after"] == "1"
    assert fresh.status_code == 200


# Criterion 3
async def test_given_the_limit_is_exceeded_when_the_database_is_read_then_no_login_request_row_was_written(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await api.request_code("test-user")
    for n in range(1, 30):
        await api.request_code(f"someone-{n}")
    written = await _rows(owner)

    for n in range(30, 50):
        assert (await api.request_code("test-user" if n % 2 else f"someone-{n}")).status_code == 429
    verify = await api.http.post("/auth/verify-code", content=b"{}", headers={"Origin": ORIGIN})

    assert written == 30  # the real one and 29 decoys (ADR-0038); the refused ones add nothing
    assert await _rows(owner) == written
    assert verify.status_code == 429


# Criterion 6
async def test_given_a_flood_from_one_client_when_refused_then_exactly_one_event_exists_per_client_and_window(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    for n in range(60):
        await api.request_code(f"someone-{n}")
    first = await _events(owner)
    api.clock.advance(timedelta(seconds=60))
    for n in range(60, 120):
        await api.request_code(f"someone-{n}")
    both = await _events(owner)

    assert len(first) == 1
    assert (first[0]["kind"], first[0]["result"], first[0]["client_key"].strip()) == (
        "rate_limited",
        "refused",
        client_hash(b"e" * 32, "203.0.113.50"),
    )
    assert first[0]["request_id"]
    assert first[0]["username_hash"] is None
    assert len(both) == 2
    assert both[0]["window"] != both[1]["window"]
