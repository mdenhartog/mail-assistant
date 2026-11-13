# pyright: reportUnusedImport=false
"""U-web-settings-17: the request-code endpoint against a real PostgreSQL, a FakeClock, FakeMailer and FakeCodes."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any

import asyncpg
import pytest
from fastapi import Request
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response

from app.auth import code_hash, login_requests
from app.auth.login_requests import LoginRequests, Ok
from app.auth.request_code import attach_request_code
from app.auth.request_code_rules import username_key
from app.core.security import inventory_violations
from app.db import Database
from app.ids import SecretsIdSource
from app.main import build_app, discover_routers
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
CODES = [f"{n:06d}" for n in range(111111, 111111 + 20 * 111111, 111111)]
PATH = "/auth/request-code"
ADDRESS = "marco@example.test"


class RecordingGuard:
    def __init__(self) -> None:
        self.buckets: list[str] = []

    async def check(self, bucket: str, request: Request) -> None:
        self.buckets.append(bucket)


@dataclass
class Api:
    http: AsyncClient
    clock: FakeClock
    mailer: FakeMailer
    store: LoginRequests
    guard: RecordingGuard

    async def request(
        self, username: object = USERNAME, origin: str | None = ORIGIN, cookie: str | None = None
    ) -> Response:
        headers = {"Origin": origin} if origin is not None else {}
        if cookie is not None:
            headers["Cookie"] = f"__Host-login={cookie}"
        return await self.http.post(PATH, json={"username": username}, headers=headers)


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    mailer = FakeMailer()
    ids = SecretsIdSource()
    settings = make_settings()
    app = build_app(settings, clock=clock, ids=ids, codes=FakeCodes(list(CODES)), mailer=mailer)
    store = LoginRequests(web_database, ids, hash_key=b"a" * 32, ttl=timedelta(seconds=600), max_attempts=5)
    attach_database(app, web_database, clock)
    attach_request_code(app, store, SecurityEvents(web_database, clock, b"e" * 32))
    guard = RecordingGuard()
    app.state.limit_guard = guard
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, clock, mailer, store, guard)


def _key(username: str) -> str:
    return username_key(b"c" * 32, username)


def _cookie(response: Response) -> tuple[str, dict[str, str]]:
    jar: SimpleCookie = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    assert list(jar) == ["__Host-login"]
    morsel = jar["__Host-login"]
    return morsel.value, {k: str(v) for k, v in morsel.items() if v}


async def _events(owner: asyncpg.Connection, kind: str) -> int:  # noqa: F811
    return await owner.fetchval("SELECT count(*) FROM web_auth.security_event WHERE kind = $1", kind)


async def _rows(owner: asyncpg.Connection) -> int:  # noqa: F811
    return await owner.fetchval("SELECT count(*) FROM web_auth.login_request")


async def test_given_the_configured_username_when_a_code_is_requested_then_200_cookie_and_one_mail(api: Api) -> None:
    response = await api.request()

    assert response.status_code == 200
    assert response.json() == {
        "maskedAddress": "m***@example.test",
        "expiresAt": "2026-03-01T14:10:00Z",
        "resendAfterSeconds": 60,
    }
    value, attributes = _cookie(response)
    assert attributes == {"httponly": "True", "secure": "True", "samesite": "Lax", "path": "/", "max-age": "600"}
    assert len(value) == 32
    assert api.mailer.sent == [(ADDRESS, "111111", T0 + timedelta(minutes=10))]
    assert ADDRESS not in response.text


async def test_given_the_cookie_when_the_code_is_checked_then_it_is_the_id_of_the_stored_request(api: Api) -> None:
    response = await api.request()

    value, _ = _cookie(response)

    assert await api.store.check(value, "111111", T0) == Ok()


async def test_given_the_configured_and_an_unknown_username_when_requested_then_the_answers_are_identical(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    known = await api.request(USERNAME)
    unknown = await api.request(UNKNOWN)

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert sorted(known.headers) == sorted(unknown.headers)
    known_value, known_attributes = _cookie(known)
    unknown_value, unknown_attributes = _cookie(unknown)
    assert known_attributes == unknown_attributes
    assert len(known_value) == len(unknown_value)
    assert known_value != unknown_value
    assert [sent[1] for sent in api.mailer.sent] == ["111111"]
    assert await _rows(owner) == 2  # the unknown username has a decoy row (ADR-0038)


async def test_given_both_cases_when_the_work_is_counted_then_the_same_steps_run(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    hashes: list[str] = []
    steps: list[str] = []

    def count_hash(original: Callable[..., bytes]) -> Callable[..., bytes]:
        def wrapper(*args: Any) -> bytes:
            hashes.append("hash")
            return original(*args)

        return wrapper

    monkeypatch.setattr(login_requests, "hash_code", count_hash(login_requests.hash_code))
    monkeypatch.setattr(code_hash, "hash_code", count_hash(code_hash.hash_code))
    # mark_sent runs after the answer; a decoy is stored by create_decoy, a real request by create. Both read the
    # limits and write the row in the one transaction of the store, so there is one step.
    for name, step in (("create", "store"), ("create_decoy", "store")):
        original = getattr(api.store, name)

        def spy(*args: Any, _name: str = step, _original: Callable[..., Awaitable[Any]] = original) -> Awaitable[Any]:
            steps.append(_name)
            return _original(*args)

        monkeypatch.setattr(api.store, name, spy)

    await api.request(USERNAME)
    known = (len(hashes), len(steps))
    hashes.clear()
    steps.clear()
    await api.request(UNKNOWN)

    assert (len(hashes), len(steps)) == known
    assert known[0] == 1


async def test_given_the_mailer_fails_when_requested_then_the_answer_is_the_same_and_the_failure_is_recorded(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    ok = await api.request(USERNAME)
    api.clock.advance(timedelta(seconds=60))
    api.mailer.fail()
    caplog.set_level(logging.DEBUG)

    failed = await api.request(USERNAME)

    assert failed.status_code == 200
    assert failed.json() == {
        "maskedAddress": "m***@example.test",
        "expiresAt": "2026-03-01T14:11:00Z",
        "resendAfterSeconds": 60,
    }
    assert _cookie(failed)[1] == _cookie(ok)[1]
    assert await _events(owner, "mail_failed") == 1
    assert len(api.mailer.sent) == 1
    assert await _rows(owner) == 2
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert ADDRESS not in logged
    assert "mail send failed" not in logged
    assert ADDRESS not in failed.text
    api.clock.advance(timedelta(seconds=30))
    assert (await api.request(USERNAME)).status_code == 429


@pytest.mark.parametrize("fail", [False, True])
async def test_given_a_second_request_at_59_and_60_seconds_when_requested_then_429_with_retry_after_1_then_200(
    api: Api, fail: bool
) -> None:
    if fail:
        api.mailer.fail()
    first = await api.request()
    first_cookie, _ = _cookie(first)

    api.clock.advance(timedelta(seconds=59))
    early = await api.request()
    api.clock.advance(timedelta(seconds=1))
    on_time = await api.request(cookie=first_cookie)

    assert early.status_code == 429
    assert early.headers["retry-after"] == "1"
    assert "set-cookie" not in early.headers
    assert on_time.status_code == 200
    assert await api.store.check(first_cookie, "111111", api.clock.now()) != Ok()
    # the refused request drew a code too (222222) and threw it away, so the issued one is the third
    assert await api.store.check(_cookie(on_time)[0], "333333", api.clock.now()) == Ok()


async def test_given_five_sent_codes_in_an_hour_when_a_sixth_is_requested_then_429_until_the_oldest_falls_out(
    api: Api,
) -> None:
    cookie: str | None = None
    for _ in range(5):
        response = await api.request(cookie=cookie)
        assert response.status_code == 200
        cookie = _cookie(response)[0]  # a browser sends the cookie it holds
        api.clock.advance(timedelta(seconds=60))
    assert len(api.mailer.sent) == 5

    sixth = await api.request(cookie=cookie)
    api.clock.set(T0 + timedelta(seconds=3599))
    late = await api.request(cookie=cookie)
    api.clock.set(T0 + timedelta(seconds=3601))
    after = await api.request(cookie=cookie)

    assert sixth.status_code == 429
    assert sixth.headers["retry-after"] == "3300"
    assert late.status_code == 429
    assert late.headers["retry-after"] == "1"
    assert after.status_code == 200
    assert len(api.mailer.sent) == 6


async def test_given_five_failed_sends_when_a_sixth_is_requested_then_it_is_refused_like_for_an_unknown_username(
    api: Api,
) -> None:
    # D-11 gave way to AC-30 (ADR-0039): a failed send counts toward the cap, so the hourly cap counts the same rows,
    # from created_at, for a real and a decoy username and a mailer outage cannot tell them apart.
    api.mailer.fail()
    cookies: dict[str, str | None] = {USERNAME: None, UNKNOWN: None}
    for _ in range(5):
        for name in (USERNAME, UNKNOWN):
            response = await api.request(name, cookie=cookies[name])
            assert response.status_code == 200
            cookies[name] = _cookie(response)[0]
        api.clock.advance(timedelta(seconds=60))
    api.mailer.succeed()

    known_sixth = await api.request(USERNAME, cookie=cookies[USERNAME])
    unknown_sixth = await api.request(UNKNOWN, cookie=cookies[UNKNOWN])

    assert known_sixth.status_code == unknown_sixth.status_code == 429
    assert known_sixth.headers["retry-after"] == unknown_sixth.headers["retry-after"]
    assert api.mailer.sent == []


async def test_given_an_unknown_username_when_requested_again_then_the_cooldown_and_the_cap_answer_like_the_known_one(
    api: Api,
) -> None:
    first = await api.request(UNKNOWN)
    assert first.status_code == 200
    cookie = _cookie(first)[0]
    api.clock.advance(timedelta(seconds=30))
    again = await api.request(UNKNOWN, cookie=cookie)
    api.clock.advance(timedelta(seconds=30))
    for _ in range(4):
        response = await api.request(UNKNOWN, cookie=cookie)
        assert response.status_code == 200
        cookie = _cookie(response)[0]
        api.clock.advance(timedelta(seconds=60))
    capped = await api.request(UNKNOWN, cookie=cookie)

    assert again.status_code == 429
    assert again.headers["retry-after"] == "30"
    assert capped.status_code == 429
    assert api.mailer.sent == []


@pytest.mark.parametrize("origin", [None, "https://evil.example", ORIGIN + "/", "null"])
async def test_given_a_wrong_or_missing_origin_when_requested_then_403_and_no_row(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    origin: str | None,
) -> None:
    response = await api.request(origin=origin)

    assert response.status_code == 403
    assert response.json() == {"type": "about:blank", "title": "Forbidden", "status": 403}
    assert await _rows(owner) == 0
    assert api.mailer.sent == []


@pytest.mark.parametrize(
    "username", ["canary-user" + "x" * 54, "bad\x00name", "bad\nname", 123, None, ["a"], {"a": 1}, "", "\x7f"]
)
async def test_given_an_invalid_username_when_requested_then_422_before_any_work_and_nothing_is_echoed(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
    username: object,
) -> None:
    caplog.set_level(logging.DEBUG)

    response = await api.request(username)

    assert response.status_code == 422
    assert response.json() == {"type": "about:blank", "title": "Unprocessable content", "status": 422}
    assert await _rows(owner) == 0
    assert api.mailer.sent == []
    assert "canary-user" not in "\n".join(record.getMessage() for record in caplog.records)


async def test_given_a_username_of_64_characters_when_requested_then_it_is_accepted(api: Api) -> None:
    assert (await api.request("u" * 64)).status_code == 200


async def test_given_a_body_with_an_extra_property_when_requested_then_422(api: Api) -> None:
    response = await api.http.post(PATH, json={"username": USERNAME, "address": "x@y.z"}, headers={"Origin": ORIGIN})

    assert response.status_code == 422


async def test_given_refused_requests_in_one_window_when_they_happen_then_one_event_is_recorded(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await api.request()
    api.clock.advance(timedelta(seconds=10))

    for _ in range(3):
        assert (await api.request()).status_code == 429

    assert await _events(owner, "code_request_refused") == 1
    row = await owner.fetchrow(
        "SELECT username_hash, result FROM web_auth.security_event WHERE kind = 'code_request_refused'"
    )
    assert row is not None
    assert row["result"] == "refused"
    assert row["username_hash"] == _key(USERNAME)


async def test_given_the_route_when_the_inventory_is_read_then_it_is_public_and_counts_against_the_signin_bucket(
    api: Api,
) -> None:
    routes = [
        (mounted.prefix + route.path, route)
        for mounted in discover_routers()
        for route in mounted.router.routes
        if isinstance(route, APIRoute) and mounted.prefix + route.path == PATH
    ]
    assert len(routes) == 1
    assert inventory_violations(routes) == []

    await api.request()

    assert api.guard.buckets == ["signin"]


async def _lock(owner: asyncpg.Connection) -> None:  # noqa: F811
    await owner.execute("INSERT INTO web_auth.web_lock (id, locked_at) VALUES (1, now())")


# Criterion 3 (AC-27, SEC-08): the lock stops the mail and the rows, the answer stays the same
async def test_given_the_web_lock_when_the_owner_asks_then_the_usual_answer_with_no_row_and_no_mail(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    usual = await api.request()
    await owner.execute("DELETE FROM web_auth.login_request")
    api.mailer.sent.clear()
    api.clock.advance(timedelta(hours=2))
    await _lock(owner)

    locked = await api.request()

    assert locked.status_code == usual.status_code == 200
    assert locked.json()["maskedAddress"] == usual.json()["maskedAddress"]
    assert locked.json()["resendAfterSeconds"] == usual.json()["resendAfterSeconds"]
    assert sorted(locked.headers) == sorted(usual.headers)
    assert _cookie(locked)[1] == _cookie(usual)[1]
    assert await _rows(owner) == 0
    assert api.mailer.sent == []


async def test_given_the_web_lock_when_a_known_and_an_unknown_username_ask_then_identical_answers_and_no_rows(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _lock(owner)

    known = await api.request(USERNAME)
    unknown = await api.request(UNKNOWN)

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert sorted(known.headers) == sorted(unknown.headers)
    assert _cookie(known)[1] == _cookie(unknown)[1]
    assert len(_cookie(known)[0]) == len(_cookie(unknown)[0])
    assert _cookie(known)[0] != _cookie(unknown)[0]
    assert await _rows(owner) == 0
    assert api.mailer.sent == []


async def test_given_the_web_lock_when_it_is_lifted_then_the_next_request_stores_a_row_and_sends_the_mail(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _lock(owner)
    await api.request()
    await owner.execute("DELETE FROM web_auth.web_lock")

    await api.request()

    assert await _rows(owner) == 1
    assert len(api.mailer.sent) == 1
