# pyright: reportUnusedImport=false
"""U-web-settings-15: session store, cookie and lock check against a real PostgreSQL and a FakeClock."""

import base64
import hashlib
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import asyncpg
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth.cookies import COOKIE_NAME, session_cookie
from app.auth.digest import username_digest
from app.auth.session import SessionStore, WebLocked, attach_sessions
from app.core.security import session
from app.db import Database
from app.ids import SecretsIdSource
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
from tests.fakes import FakeClock, make_app, real_minute

T0 = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _t0_is_the_real_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.modules[__name__], "T0", real_minute())  # the event window is checked by the database


USER = username_digest(b"k" * 32, "canary-user")
CLIENT = "203.0.113.7"
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def events(web_database: Database, clock: FakeClock) -> SecurityEvents:  # noqa: F811
    return SecurityEvents(web_database, clock, b"e" * 32)


@pytest.fixture
def store(web_database: Database, events: SecurityEvents) -> SessionStore:  # noqa: F811
    return SessionStore(web_database, SecretsIdSource(), events)


@pytest.fixture
async def api(
    web_database: Database,  # noqa: F811
    clock: FakeClock,
    store: SessionStore,
    events: SecurityEvents,
) -> AsyncIterator[AsyncClient]:
    app: FastAPI = make_app()
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, events)

    @app.get("/t/protected", dependencies=[Depends(session)])
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def _rows(owner: asyncpg.Connection) -> list[asyncpg.Record]:  # noqa: F811
    return await owner.fetch("select * from web_auth.session")


async def _events(owner: asyncpg.Connection, kind: str) -> list[asyncpg.Record]:  # noqa: F811
    return await owner.fetch("select * from web_auth.security_event where kind = $1", kind)


# Criterion 1
def test_given_a_created_session_when_the_cookie_is_built_then_it_has_the_host_attributes() -> None:
    value = SecretsIdSource().session_id()

    header = session_cookie(value)

    jar: SimpleCookie = SimpleCookie()
    jar.load(header)
    morsel = jar[COOKIE_NAME]
    assert COOKIE_NAME == "__Host-session"
    assert morsel.value == value
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"] == "Lax"
    assert morsel["path"] == "/"
    assert morsel["domain"] == ""
    assert morsel["max-age"] == "43200"
    assert len(base64.urlsafe_b64decode(value + "=")) == 32


# Criterion 2
async def test_given_a_session_last_seen_at_14_00_when_used_at_14_29_59_and_14_30_00_then_accepted_then_gone(
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, _ = await store.create(USER, T0)

    at_29_59 = await store.get(cookie, T0 + timedelta(minutes=29, seconds=59))
    at_30_00 = await store.get(cookie, T0 + timedelta(minutes=30))

    assert at_29_59 is not None
    assert at_30_00 is None
    assert await _rows(owner) == []


# Criterion 3
async def test_given_activity_every_20_minutes_when_used_at_19_59_59_and_20_00_00_then_accepted_then_gone(
    store: SessionStore,
) -> None:
    start = datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC)
    cookie, _ = await store.create(USER, start)
    for step in range(1, 36):
        moment = start + timedelta(minutes=20 * step)
        found = await store.get(cookie, moment)
        assert found is not None
        await store.touch(found, moment)

    before = await store.get(cookie, start + timedelta(hours=12, seconds=-1))
    after = await store.get(cookie, start + timedelta(hours=12))

    assert before is not None
    assert after is None


# Criterion 4
async def test_given_two_sign_ins_when_both_create_sessions_then_the_ids_differ_and_a_foreign_cookie_is_not_adopted(
    store: SessionStore,
) -> None:
    foreign = "attacker-chosen-value"

    first, _ = await store.create(USER, T0)
    second, _ = await store.create(USER, T0)

    assert first != second
    assert foreign not in {first, second}
    assert await store.get(foreign, T0) is None
    assert await store.get(first, T0) is not None


# Criterion 5
async def test_given_the_table_read_as_the_owner_when_inspected_then_only_the_hash_and_the_digest_are_stored(
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, created = await store.create(USER, T0)

    rows = await _rows(owner)

    assert len(rows) == 1
    row = rows[0]
    assert row["id_hash"].strip() == hashlib.sha256(cookie.encode()).hexdigest()
    assert row["username_hash"].strip() == USER
    assert cookie not in repr(tuple(row.values()))
    assert "canary-user" not in repr(tuple(row.values()))
    assert created.id_hash == row["id_hash"].strip()
    assert created.username_hash == USER
    assert created.absolute_expires_at == T0 + timedelta(hours=12)


# Criterion 6
@pytest.mark.parametrize("kind", ["no cookie", "unknown cookie", "expired session"])
async def test_given_no_unknown_or_expired_session_when_a_protected_route_is_called_then_401_with_the_generic_body(
    kind: str, api: AsyncClient, store: SessionStore, clock: FakeClock
) -> None:
    cookies: dict[str, str] = {}
    if kind == "unknown cookie":
        cookies = {COOKIE_NAME: "unknown"}
    if kind == "expired session":
        value, _ = await store.create(USER, T0)
        cookies = {COOKIE_NAME: value}
        clock.advance(timedelta(minutes=30))

    response = await api.get("/t/protected", cookies=cookies)

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == GENERIC_401


# Criterion 7
async def test_given_web_lock_set_when_a_valid_session_calls_then_401_sessions_deleted_and_one_event_per_window(
    api: AsyncClient,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    value, _ = await store.create(USER, T0)
    other, _ = await store.create(USER, T0)
    assert (await api.get("/t/protected", cookies={COOKIE_NAME: value})).status_code == 200
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", T0)

    first = await api.get("/t/protected", cookies={COOKIE_NAME: value})
    second = await api.get("/t/protected", cookies={COOKIE_NAME: other})

    assert first.status_code == 401
    assert second.status_code == 401
    assert first.json() == second.json() == GENERIC_401
    assert await _rows(owner) == []
    assert len(await _events(owner, "lock_refused")) == 1


async def test_given_web_lock_set_when_the_store_is_asked_then_it_raises_and_deletes_the_sessions(
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    value, _ = await store.create(USER, T0)
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", T0)

    with pytest.raises(WebLocked):
        await store.get(value, T0)

    assert await _rows(owner) == []


# Criterion 8
async def test_given_an_authorised_request_when_served_then_last_seen_moves_to_the_clock_now(
    api: AsyncClient,
    store: SessionStore,
    clock: FakeClock,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    value, _ = await store.create(USER, T0)
    clock.advance(timedelta(minutes=10))

    response = await api.get("/t/protected", cookies={COOKIE_NAME: value})

    assert response.status_code == 200
    (row,) = await _rows(owner)
    assert row["last_seen_at"] == T0 + timedelta(minutes=10)
    assert row["absolute_expires_at"] == T0 + timedelta(hours=12)


# Criterion 9
async def test_given_the_logout_path_when_a_session_is_deleted_then_a_session_end_event_is_recorded(
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    value, _ = await store.create(USER, T0)

    await store.delete(value, "req-1", CLIENT)

    assert await store.get(value, T0) is None
    assert await _rows(owner) == []
    (event,) = await _events(owner, "session_end")
    assert event["username_hash"].strip() == USER
    assert event["request_id"] == "req-1"
    assert value not in repr(tuple(event.values()))


async def test_given_a_session_when_read_then_created_at_is_the_sign_in_time_and_touch_of_a_gone_one_is_a_noop(
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    value, created = await store.create(USER, T0)
    found = await store.get(value, T0)
    await store.delete(value, "req-1", CLIENT)

    await store.touch(created, T0 + timedelta(minutes=1))

    assert found is not None
    assert found.created_at == T0
    assert await _rows(owner) == []


async def test_given_an_unknown_cookie_when_deleted_then_no_event_is_recorded(
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await store.delete("unknown", "req-1", CLIENT)

    assert await _events(owner, "session_end") == []


async def test_given_web_lock_set_when_a_session_is_created_then_it_raises_and_nothing_is_stored(
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", T0)

    with pytest.raises(WebLocked):
        await store.create(USER, T0)

    assert await _rows(owner) == []
