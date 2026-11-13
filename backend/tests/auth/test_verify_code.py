# pyright: reportUnusedImport=false
"""U-web-settings-18: the verify-code endpoint against a real PostgreSQL, a FakeClock, FakeMailer and FakeCodes."""

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any

import asyncpg
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient, Response

from app.auth.cookies import clear_login_cookie
from app.auth.digest import username_digest
from app.auth.login_requests import LoginRequests
from app.auth.request_code import attach_request_code
from app.auth.session import SessionStore, attach_sessions
from app.auth.verify_code import attach_verify_code
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
USERNAME = "test-user"
UNKNOWN = "somebody-else"
FIRST = "111111"
SECOND = "222222"
CANARY = "424242"
CODES = [f"{n:06d}" for n in range(111111, 111111 + 20 * 111111, 111111)]
REQUEST_CODE = "/auth/request-code"
VERIFY = "/auth/verify-code"
GENERIC = {"type": "about:blank", "title": "Bad request", "status": 400}


class RecordingGuard:
    def __init__(self) -> None:
        self.buckets: list[str] = []

    async def check(self, bucket: str, request: Request) -> None:
        self.buckets.append(bucket)


@dataclass
class Api:
    http: AsyncClient
    clock: FakeClock
    guard: RecordingGuard
    logins: LoginRequests

    async def issue(self, username: str = USERNAME) -> str:
        """Ask for a code and return the value of the login cookie."""
        response = await self.http.post(REQUEST_CODE, json={"username": username}, headers={"Origin": ORIGIN})
        assert response.status_code == 200
        jar: SimpleCookie = SimpleCookie()
        jar.load(response.headers["set-cookie"])
        return jar["__Host-login"].value

    async def verify(
        self,
        code: object,
        cookie: str | None,
        *,
        origin: str | None = ORIGIN,
        extra: dict[str, Any] | None = None,
        content: bytes | None = None,
    ) -> Response:
        headers: dict[str, str] = {}
        if origin is not None:
            headers["Origin"] = origin
        if cookie is not None:
            headers["Cookie"] = f"__Host-login={cookie}"
        if content is not None:
            headers["Content-Type"] = "application/json"
            return await self.http.post(VERIFY, content=content, headers=headers)
        return await self.http.post(VERIFY, json={"code": code, **(extra or {})}, headers=headers)


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    ids = SecretsIdSource()
    settings = make_settings()
    app = build_app(settings, clock=clock, ids=ids, codes=FakeCodes(list(CODES)), mailer=FakeMailer())
    events = SecurityEvents(web_database, clock, b"e" * 32)
    logins = LoginRequests(web_database, ids, hash_key=b"a" * 32, ttl=timedelta(seconds=600), max_attempts=5)
    sessions = SessionStore(web_database, ids, events)
    attach_database(app, web_database, clock)
    attach_request_code(app, logins, events)
    attach_sessions(app, sessions, events)
    attach_verify_code(app, logins, sessions, events)
    guard = RecordingGuard()
    app.state.limit_guard = guard
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, clock, guard, logins)


def _set_cookies(response: Response) -> dict[str, SimpleCookie]:
    cookies: dict[str, SimpleCookie] = {}
    for header in response.headers.get_list("set-cookie"):
        jar: SimpleCookie = SimpleCookie()
        jar.load(header)
        for name in jar:
            cookies[name] = jar  # type: ignore[assignment]
    return cookies


def _assert_login_cleared(response: Response) -> None:
    morsel = _set_cookies(response)["__Host-login"]["__Host-login"]
    assert morsel.value == ""
    assert morsel["max-age"] == "0"
    assert morsel["path"] == "/"
    assert morsel["secure"] is True
    assert morsel["httponly"] is True


def _assert_refused(response: Response) -> None:
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert {key: value for key, value in response.json().items() if key != "attemptsLeft"} == GENERIC
    assert "__Host-session" not in _set_cookies(response)


async def _sessions(owner: asyncpg.Connection) -> int:  # noqa: F811
    return await owner.fetchval("SELECT count(*) FROM web_auth.session")


async def _events(owner: asyncpg.Connection, kind: str) -> list[asyncpg.Record]:  # noqa: F811
    return await owner.fetch("SELECT * FROM web_auth.security_event WHERE kind = $1", kind)


def test_given_the_login_cookie_when_cleared_then_it_has_the_host_attributes_and_expires_now() -> None:
    jar: SimpleCookie = SimpleCookie()
    jar.load(clear_login_cookie())

    morsel = jar["__Host-login"]
    assert morsel.value == ""
    assert morsel["max-age"] == "0"
    assert morsel["expires"] == "Thu, 01 Jan 1970 00:00:00 GMT"
    assert morsel["path"] == "/"
    assert morsel["domain"] == ""
    assert morsel["secure"] is True
    assert morsel["httponly"] is True
    assert morsel["samesite"] == "Lax"


# Criterion 1
async def test_given_a_requested_code_when_the_right_code_is_posted_then_204_session_and_event(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue()

    response = await api.verify(FIRST, cookie)

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["x-return-to"] == "/settings"
    cookies = _set_cookies(response)
    morsel = cookies["__Host-session"]["__Host-session"]
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"] == "Lax"
    assert morsel["path"] == "/"
    assert morsel["max-age"] == "43200"
    _assert_login_cleared(response)
    row = await owner.fetchrow("SELECT * FROM web_auth.session")
    assert row is not None
    assert row["id_hash"] == hashlib.sha256(morsel.value.encode()).hexdigest()
    assert str(row["username_hash"]).strip() == username_digest(b"c" * 32, USERNAME)
    started = await _events(owner, "session_start")
    assert len(started) == 1
    assert started[0]["result"] == "ok"
    assert started[0]["username_hash"].strip() == username_digest(b"c" * 32, USERNAME)
    assert api.guard.buckets[-1:] == ["signin"]


# Criterion 2
async def test_given_a_wrong_code_when_posted_then_the_generic_400_and_no_session(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue()

    response = await api.verify(SECOND, cookie)

    _assert_refused(response)
    assert await _sessions(owner) == 0


async def test_given_an_expired_code_when_posted_at_10_00_then_the_generic_400_and_no_session(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue()
    api.clock.advance(timedelta(minutes=10))

    response = await api.verify(FIRST, cookie)

    _assert_refused(response)
    assert "attemptsLeft" not in response.json()
    assert await _sessions(owner) == 0


async def test_given_a_used_code_when_posted_again_then_the_generic_400_and_one_session(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue()
    assert (await api.verify(FIRST, cookie)).status_code == 204

    response = await api.verify(FIRST, cookie)

    _assert_refused(response)
    assert await _sessions(owner) == 1


async def test_given_five_wrong_attempts_when_the_right_code_is_posted_then_the_generic_400(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue()
    for _ in range(5):
        await api.verify(SECOND, cookie)

    response = await api.verify(FIRST, cookie)

    _assert_refused(response)
    assert await _sessions(owner) == 0


async def test_given_a_cookie_of_another_browser_when_the_code_is_posted_then_the_generic_400(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await api.issue()

    response = await api.verify(FIRST, "x" * 32)

    _assert_refused(response)
    assert await _sessions(owner) == 0


async def test_given_an_old_code_after_a_new_one_when_posted_then_the_generic_400(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    old = await api.issue()
    api.clock.advance(timedelta(seconds=61))
    await api.issue()

    response = await api.verify(FIRST, old)

    _assert_refused(response)
    assert await _sessions(owner) == 0


async def test_given_the_cookie_of_an_unknown_username_when_a_code_is_posted_then_the_generic_400(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue(UNKNOWN)

    response = await api.verify(FIRST, cookie)

    _assert_refused(response)
    assert await _sessions(owner) == 0


async def test_given_no_cookie_when_a_code_is_posted_then_the_generic_400(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await api.issue()

    response = await api.verify(FIRST, None)

    _assert_refused(response)
    assert await _sessions(owner) == 0


@pytest.mark.parametrize("cookie", ["a" * 400, "bad value%00", "x" * 31 + "-e"])
async def test_given_a_malformed_cookie_value_when_a_code_is_posted_then_the_generic_400_not_a_500(
    api: Api, cookie: str
) -> None:
    response = await api.http.post(
        VERIFY, json={"code": FIRST}, headers={"Origin": ORIGIN, "Cookie": f"__Host-login={cookie}"}
    )

    _assert_refused(response)


# Criterion 3
async def test_given_wrong_codes_on_a_live_request_when_refused_then_attempts_left_counts_down_then_it_is_dead(
    api: Api,
) -> None:
    cookie = await api.issue()

    lefts: list[int] = []
    for _ in range(4):
        response = await api.verify(SECOND, cookie)
        _assert_refused(response)
        lefts.append(response.json()["attemptsLeft"])
        assert "__Host-login" not in _set_cookies(response)
    fifth = await api.verify(SECOND, cookie)
    sixth = await api.verify(FIRST, cookie)

    assert lefts == [4, 3, 2, 1]
    _assert_refused(fifth)
    assert "attemptsLeft" not in fifth.json()
    _assert_login_cleared(fifth)
    _assert_refused(sixth)
    assert "attemptsLeft" not in sixth.json()


async def test_given_no_cookie_or_a_dead_request_when_refused_then_there_is_no_attempts_left_field(api: Api) -> None:
    none = await api.verify(SECOND, None)
    cookie = await api.issue()
    assert (await api.verify(FIRST, cookie)).status_code == 204
    dead = await api.verify(SECOND, cookie)

    for response in (none, dead):
        _assert_refused(response)
        assert response.json() == GENERIC
        _assert_login_cleared(response)


# Criterion 4
async def test_given_two_concurrent_requests_with_the_right_code_when_run_then_one_204_one_400_one_session(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue()

    first, second = await asyncio.gather(api.verify(FIRST, cookie), api.verify(FIRST, cookie))

    assert sorted([first.status_code, second.status_code]) == [204, 400]
    assert await _sessions(owner) == 1


# Criterion 5
@pytest.mark.parametrize("value", ["https://evil.example", "//x", "javascript:1", "/other", ""])
async def test_given_a_return_to_outside_the_allow_list_when_the_right_code_is_posted_then_settings(
    api: Api, value: str
) -> None:
    cookie = await api.issue()

    response = await api.verify(FIRST, cookie, extra={"returnTo": value})

    assert response.status_code == 204
    assert response.headers["x-return-to"] == "/settings"


# Criterion 6
async def test_given_the_web_lock_when_the_right_code_is_posted_then_the_answer_of_a_dead_request_and_no_session(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    reference = await api.verify(SECOND, None)
    cookie = await api.issue()
    await owner.execute("INSERT INTO web_auth.web_lock (id, locked_at) VALUES (1, now())")

    response = await api.verify(FIRST, cookie)

    assert response.status_code == reference.status_code == 400
    assert response.json() == reference.json()
    assert response.headers.get_list("set-cookie") == reference.headers.get_list("set-cookie")
    differing = {
        name
        for name in set(response.headers) | set(reference.headers)
        if response.headers.get(name) != reference.headers.get(name)
    }
    assert differing <= {"x-request-id"}
    assert await _sessions(owner) == 0
    assert len(await _events(owner, "lock_refused")) == 1
    assert await _events(owner, "session_start") == []


# Criterion 7
@pytest.mark.parametrize("origin", [None, "https://evil.example", "null", ORIGIN + "/"])
async def test_given_a_wrong_or_missing_origin_when_posted_then_403_and_no_attempt_is_counted(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    origin: str | None,
) -> None:
    cookie = await api.issue()

    response = await api.verify(FIRST, cookie, origin=origin)

    assert response.status_code == 403
    assert await owner.fetchval("SELECT attempts FROM web_auth.login_request") == 0
    assert await _sessions(owner) == 0


# Criterion 8
async def test_given_refused_codes_when_events_are_read_then_one_per_window_and_no_code_or_cookie(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    cookie = await api.issue()

    for _ in range(3):
        await api.verify(CANARY, cookie)

    refused = await _events(owner, "code_refused")
    assert len(refused) == 1
    assert refused[0]["result"] == "refused"
    text = " ".join(str(value) for value in refused[0].values())
    assert CANARY not in text
    assert cookie not in text
    assert CANARY not in caplog.text
    assert cookie not in caplog.text


# Criterion 9
@pytest.mark.parametrize("code", ["1234567", "abcdef", "", {"a": 1}, 123456, None, "12345"])
async def test_given_a_malformed_code_when_posted_then_the_generic_400_and_the_attempt_is_not_counted(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    code: object,
) -> None:
    cookie = await api.issue()

    response = await api.verify(code, cookie)

    _assert_refused(response)
    assert await owner.fetchval("SELECT attempts FROM web_auth.login_request") == 0
    assert response.json()["attemptsLeft"] == 5
    assert await _sessions(owner) == 0


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not json",
        b"[]",
        b'"123456"',
        b"{}",
        b'{"code": "111111", "extra": 1}',
        b'{"code": "111111", "returnTo": {}}',
    ],
)
async def test_given_a_malformed_body_when_posted_then_the_generic_400_and_no_session(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    content: bytes,
) -> None:
    cookie = await api.issue()

    response = await api.verify(None, cookie, content=content)

    _assert_refused(response)
    assert await owner.fetchval("SELECT attempts FROM web_auth.login_request") == 0
    assert await _sessions(owner) == 0
