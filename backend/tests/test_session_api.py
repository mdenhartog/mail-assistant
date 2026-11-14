# pyright: reportUnusedImport=false
"""U-web-settings-19: GET /api/session, the CSRF and Origin checks and POST /auth/logout against a real PostgreSQL."""

import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.cookies import COOKIE_NAME, clear_session_cookie
from app.auth.csrf import csrf_token
from app.auth.digest import username_digest
from app.auth.session import SessionStore, attach_sessions
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
from tests.fakes import FakeClock, make_app, make_settings, real_minute

T0 = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _t0_is_the_real_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.modules[__name__], "T0", real_minute())  # the event window is checked by the database


USER = username_digest(b"k" * 32, "canary-user")
ORIGIN = "https://settings.example.test"
CSRF_KEY = b"b" * 32
GENERIC_403 = {"type": "about:blank", "title": "Forbidden", "status": 403}
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
    app = make_app(make_settings(notice_interval_minutes=3))
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, events)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def _sessions(owner: asyncpg.Connection) -> list[asyncpg.Record]:  # noqa: F811
    return await owner.fetch("select * from web_auth.session")


async def _events(owner: asyncpg.Connection, kind: str) -> list[asyncpg.Record]:  # noqa: F811
    return await owner.fetch("select * from web_auth.security_event where kind = $1", kind)


async def _signed_in(store: SessionStore) -> tuple[str, str]:
    """Create a session; return its cookie value and its CSRF token."""
    cookie, created = await store.create(USER, T0)
    return cookie, csrf_token(CSRF_KEY, created.id_hash)


def _write_headers(token: str | None, origin: str | None = ORIGIN) -> dict[str, str]:
    headers: dict[str, str] = {}
    if token is not None:
        headers["X-CSRF-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    return headers


# Criterion 2
async def test_given_a_same_origin_get_when_answered_then_it_carries_the_masked_address_token_and_times(
    api: AsyncClient, store: SessionStore
) -> None:
    cookie, token = await _signed_in(store)

    response = await api.get("/api/session", cookies={COOKIE_NAME: cookie}, headers={"Sec-Fetch-Site": "same-origin"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"maskedAddress", "csrfToken", "idleExpiresAt", "absoluteExpiresAt", "noticeIntervalMinutes"}
    assert body["maskedAddress"] == "m***@example.test"
    assert body["csrfToken"] == token
    assert datetime.fromisoformat(body["idleExpiresAt"]) == T0 + timedelta(minutes=30)
    assert datetime.fromisoformat(body["absoluteExpiresAt"]) == T0 + timedelta(hours=12)
    assert body["noticeIntervalMinutes"] == 3
    assert "test-user" not in response.text
    assert "marco@example.test" not in response.text


async def test_given_a_get_without_fetch_metadata_when_answered_then_it_is_served(
    api: AsyncClient, store: SessionStore
) -> None:
    cookie, _ = await _signed_in(store)

    response = await api.get("/api/session", cookies={COOKIE_NAME: cookie})

    assert response.status_code == 200


async def test_given_no_session_when_the_session_is_read_then_401(api: AsyncClient) -> None:
    response = await api.get("/api/session")

    assert response.status_code == 401
    assert response.json() == GENERIC_401


async def test_given_a_session_near_the_absolute_limit_when_read_then_the_idle_time_is_capped_by_it(
    api: AsyncClient, store: SessionStore, clock: FakeClock
) -> None:
    cookie, _ = await _signed_in(store)
    for _ in range(24):  # active every 29 minutes: 11 hours 36 minutes after sign-in
        clock.advance(timedelta(minutes=29))
        assert (await api.get("/api/session", cookies={COOKIE_NAME: cookie})).status_code == 200
    clock.advance(timedelta(minutes=20))  # 11 hours 56 minutes: 4 minutes before the absolute limit

    body = (await api.get("/api/session", cookies={COOKIE_NAME: cookie})).json()

    assert datetime.fromisoformat(body["idleExpiresAt"]) == T0 + timedelta(hours=12)


# Criterion 3
@pytest.mark.parametrize("site", ["cross-site", "same-site", "none"])
async def test_given_a_foreign_fetch_site_when_the_session_is_read_then_403_without_a_token(
    site: str,
    api: AsyncClient,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, token = await _signed_in(store)

    response = await api.get("/api/session", cookies={COOKIE_NAME: cookie}, headers={"Sec-Fetch-Site": site})

    assert response.status_code == 403
    assert response.json() == GENERIC_403
    assert token not in response.text
    assert "csrfToken" not in response.text
    assert len(await _events(owner, "csrf_refused")) == 1


# Criterion 4
@pytest.mark.parametrize("kind", ["missing", "wrong", "other session", "empty"])
async def test_given_a_write_with_a_bad_token_when_sent_then_403_with_one_body_and_the_session_stays(
    kind: str,
    api: AsyncClient,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, token = await _signed_in(store)
    _, other = await store.create(USER, T0)
    presented = {
        "missing": None,
        "wrong": token[:-1] + ("0" if token[-1] != "0" else "1"),
        "other session": csrf_token(CSRF_KEY, other.id_hash),
        "empty": "",
    }[kind]

    response = await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers(presented))

    assert response.status_code == 403
    assert response.json() == GENERIC_403
    assert len(await _sessions(owner)) == 2
    assert (await api.get("/api/session", cookies={COOKIE_NAME: cookie})).status_code == 200


# Criterion 5
@pytest.mark.parametrize(
    "origin", [None, "null", "https://evil.test", "http://settings.example.test", ORIGIN + ".evil.test"]
)
async def test_given_a_valid_token_with_a_bad_origin_when_sent_then_403_and_nothing_changes(
    origin: str | None,
    api: AsyncClient,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, token = await _signed_in(store)

    response = await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers(token, origin))

    assert response.status_code == 403
    assert response.json() == GENERIC_403
    assert len(await _sessions(owner)) == 1


async def test_given_a_valid_token_and_origin_with_cross_site_fetch_metadata_when_sent_then_403(
    api: AsyncClient,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, token = await _signed_in(store)
    headers = _write_headers(token) | {"Sec-Fetch-Site": "cross-site"}

    response = await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=headers)

    assert response.status_code == 403
    assert len(await _sessions(owner)) == 1


async def test_given_no_session_when_a_write_is_sent_then_401_before_any_csrf_check(
    api: AsyncClient,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    response = await api.post("/auth/logout", headers=_write_headers("whatever"))

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert await _events(owner, "csrf_refused") == []


# Criterion 6
async def test_given_a_get_on_the_logout_route_when_sent_then_405_and_the_session_stays(
    api: AsyncClient,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, token = await _signed_in(store)

    response = await api.get("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers(token))

    assert response.status_code == 405
    assert len(await _sessions(owner)) == 1


# Criterion 7
async def test_given_a_valid_logout_when_sent_then_204_the_session_is_gone_and_the_cookie_is_cleared(
    api: AsyncClient,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, token = await _signed_in(store)

    response = await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers(token))

    assert response.status_code == 204
    assert response.content == b""
    jar: SimpleCookie = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    morsel = jar[COOKIE_NAME]
    assert morsel.value == ""
    assert morsel["max-age"] == "0"
    assert morsel["secure"] is True
    assert morsel["httponly"] is True
    assert morsel["path"] == "/"
    assert morsel["domain"] == ""
    assert await _sessions(owner) == []
    assert len(await _events(owner, "session_end")) == 1
    old = await api.get("/api/session", cookies={COOKIE_NAME: cookie})
    assert old.status_code == 401


async def test_given_a_logout_without_the_token_when_sent_then_403_and_the_session_stays_valid(
    api: AsyncClient, store: SessionStore
) -> None:
    cookie, _ = await _signed_in(store)

    response = await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers(None))

    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert (await api.get("/api/session", cookies={COOKIE_NAME: cookie})).status_code == 200


def test_given_the_clear_helper_when_built_then_it_expires_the_host_cookie_at_once() -> None:
    jar: SimpleCookie = SimpleCookie()
    jar.load(clear_session_cookie())

    morsel = jar[COOKIE_NAME]
    assert morsel.value == ""
    assert morsel["max-age"] == "0"
    assert morsel["expires"] == "Thu, 01 Jan 1970 00:00:00 GMT"
    assert morsel["secure"] is True
    assert morsel["httponly"] is True
    assert morsel["samesite"] == "Lax"
    assert morsel["path"] == "/"
    assert morsel["domain"] == ""


# Criterion 8
async def test_given_two_tabs_of_one_session_when_both_fetch_the_token_then_it_is_the_same_and_either_works(
    api: AsyncClient, store: SessionStore
) -> None:
    cookie, _ = await _signed_in(store)

    tab_a = (await api.get("/api/session", cookies={COOKIE_NAME: cookie})).json()["csrfToken"]
    tab_b = (await api.get("/api/session", cookies={COOKIE_NAME: cookie})).json()["csrfToken"]
    response = await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers(tab_b))

    assert tab_a == tab_b
    assert response.status_code == 204


# Criterion 9
async def test_given_a_preflight_or_any_response_when_inspected_then_there_is_no_cors_header(
    api: AsyncClient, store: SessionStore
) -> None:
    cookie, token = await _signed_in(store)
    foreign = {"Origin": "https://evil.test", "Access-Control-Request-Method": "POST"}
    forged = _write_headers(None, "https://evil.test")

    responses = [
        await api.options("/auth/logout", headers=foreign),
        await api.options("/api/session", headers=foreign),
        await api.get("/api/session", cookies={COOKIE_NAME: cookie}, headers={"Origin": ORIGIN}),
        await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=forged),
        await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers(token)),
    ]

    assert [r.status_code for r in responses] == [405, 405, 200, 403, 204]
    for response in responses:
        assert not [name for name in response.headers if name.lower().startswith("access-control-")]


async def test_given_two_refusals_of_one_client_when_in_one_window_then_one_event_and_a_new_window_a_second(
    api: AsyncClient,
    store: SessionStore,
    clock: FakeClock,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie, _ = await _signed_in(store)

    for _ in range(3):
        await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers("bad"))
    assert len(await _events(owner, "csrf_refused")) == 1
    clock.advance(timedelta(seconds=60))
    await api.post("/auth/logout", cookies={COOKIE_NAME: cookie}, headers=_write_headers("bad"))

    rows = await _events(owner, "csrf_refused")
    assert len(rows) == 2
    assert {row["username_hash"].strip() for row in rows} == {USER}
