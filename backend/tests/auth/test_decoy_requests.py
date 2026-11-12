# pyright: reportUnusedImport=false
"""U-web-settings-50: decoy login requests for unknown usernames, against a real PostgreSQL (ADR-0038, W-2)."""

import statistics
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Final

import asyncpg
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient, Response

from app.auth.code_hash import hash_code
from app.auth.login_requests import RETENTION, LoginRequests
from app.auth.request_code import CodeRequests, attach_request_code
from app.auth.request_code_rules import username_key
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

T0: Final = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)
ORIGIN: Final = "https://settings.example.test"
USERNAME: Final = "test-user"
UNKNOWN: Final = "somebody-else"
CODES: Final = [f"{n:06d}" for n in range(111111, 111111 + 80 * 11111, 11111)]
REQUEST_CODE: Final = "/auth/request-code"
VERIFY: Final = "/auth/verify-code"
GENERIC: Final = {"type": "about:blank", "title": "Bad request", "status": 400}
WRONG: Final = "000001"
CAP: Final = 100  # open_login_request_cap of the default settings
# Timing: the two medians may differ by at most this share of the larger one, or this many seconds when the larger
# one is tiny. Samples alternate between the two paths, so a slow moment of the machine hits both.
SAMPLES: Final = 25
WARM_UP: Final = 3
NOISE_SHARE: Final = 0.5
NOISE_FLOOR_SECONDS: Final = 0.005


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
    requests: CodeRequests
    guard: RecordingGuard

    async def request_code(self, username: str) -> Response:
        return await self.http.post(REQUEST_CODE, json={"username": username}, headers={"Origin": ORIGIN})

    async def issue(self, username: str) -> str:
        response = await self.request_code(username)
        assert response.status_code == 200
        return _cookie(response)

    async def verify(self, code: object, cookie: str) -> Response:
        return await self.http.post(
            VERIFY, json={"code": code}, headers={"Origin": ORIGIN, "Cookie": f"__Host-login={cookie}"}
        )


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    mailer = FakeMailer()
    ids = SecretsIdSource()
    app = build_app(make_settings(), clock=clock, ids=ids, codes=FakeCodes(list(CODES)), mailer=mailer)
    events = SecurityEvents(web_database, clock)
    logins = LoginRequests(web_database, ids, hash_key=b"a" * 32, ttl=timedelta(seconds=600), max_attempts=5)
    sessions = SessionStore(web_database, ids, events)
    attach_database(app, web_database, clock)
    attach_request_code(app, logins, events)
    attach_sessions(app, sessions, events)
    attach_verify_code(app, logins, sessions, events)
    guard = RecordingGuard()
    app.state.limit_guard = guard
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, clock, mailer, app.state.code_requests, guard)


def _cookie(response: Response) -> str:
    jar: SimpleCookie = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    return jar["__Host-login"].value


def _shape(response: Response) -> tuple[int, dict[str, object], list[str], dict[str, str]]:
    """What a visitor sees of an answer; the id and the expiry time differ by nature and are compared apart."""
    body = {key: value for key, value in response.json().items() if key != "expiresAt"}
    jar: SimpleCookie = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    attributes = {key: str(value) for key, value in jar["__Host-login"].items() if value}
    return response.status_code, body, sorted(response.headers), attributes


async def _rows(owner: asyncpg.Connection) -> int:  # noqa: F811
    return await owner.fetchval("SELECT count(*) FROM web_auth.login_request")


async def _sessions(owner: asyncpg.Connection) -> int:  # noqa: F811
    return await owner.fetchval("SELECT count(*) FROM web_auth.session")


# Criterion 1
async def test_given_an_unknown_and_a_known_username_when_requested_then_same_answer_and_only_known_is_mailed(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    known = await api.request_code(USERNAME)
    unknown = await api.request_code(UNKNOWN)

    assert _shape(known) == _shape(unknown)
    assert known.json()["expiresAt"] == unknown.json()["expiresAt"]
    assert _cookie(known) != _cookie(unknown)
    assert len(_cookie(unknown)) == 32
    assert [sent[1] for sent in api.mailer.sent] == ["111111"]
    assert await _rows(owner) == 2


# Criterion 1
async def test_given_a_known_and_an_unknown_username_when_requested_again_then_the_cooldown_answers_the_same(
    api: Api,
) -> None:
    await api.request_code(USERNAME)
    await api.request_code(UNKNOWN)
    api.clock.advance(timedelta(seconds=59))

    known = await api.request_code(USERNAME)
    unknown = await api.request_code(UNKNOWN)
    api.clock.advance(timedelta(seconds=1))
    known_later = await api.request_code(USERNAME)
    unknown_later = await api.request_code(UNKNOWN)

    assert known.status_code == unknown.status_code == 429
    assert known.headers["retry-after"] == unknown.headers["retry-after"] == "1"
    assert known.content == unknown.content
    assert known_later.status_code == unknown_later.status_code == 200
    assert _shape(known_later) == _shape(unknown_later)


# Criterion 2
async def test_given_a_decoy_when_wrong_codes_are_posted_then_attempts_left_counts_down_and_the_fifth_kills_it(
    api: Api,
) -> None:
    real = await api.issue(USERNAME)
    decoy = await api.issue(UNKNOWN)

    answers = [(await api.verify(WRONG, real), await api.verify(WRONG, decoy)) for _ in range(5)]

    assert [pair[1].json().get("attemptsLeft") for pair in answers] == [4, 3, 2, 1, None]
    for real_answer, decoy_answer in answers:
        assert real_answer.status_code == decoy_answer.status_code == 400
        assert real_answer.json() == decoy_answer.json()
        assert real_answer.headers.get_list("set-cookie") == decoy_answer.headers.get_list("set-cookie")
    assert "max-age=0" in answers[4][1].headers["set-cookie"].lower()
    assert "attemptsLeft" not in (await api.verify(WRONG, decoy)).json()


# Criterion 3
@pytest.mark.parametrize("code", ["111111", "222222", "000000", "123456", "999999", "111112"])
async def test_given_a_decoy_when_any_code_is_posted_then_it_is_refused_generically_and_no_session_is_made(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    code: str,
) -> None:
    cookie = await api.issue(UNKNOWN)

    response = await api.verify(code, cookie)

    assert response.status_code == 400
    assert response.json() == {**GENERIC, "attemptsLeft": 4}
    assert "__Host-session" not in "".join(response.headers.get_list("set-cookie"))
    assert await _sessions(owner) == 0


# Criterion 3
async def test_given_a_decoy_when_the_codes_a_real_request_would_have_got_are_posted_then_all_are_refused(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue(UNKNOWN)

    for code in CODES[:4]:
        assert (await api.verify(code, cookie)).status_code == 400

    assert await _sessions(owner) == 0


# Criterion 4
@pytest.mark.parametrize("bad", ["12345", "1234567", "abcdef", "12 456", ""])
async def test_given_a_wrong_format_code_when_posted_to_a_decoy_and_a_real_request_then_the_answers_match(
    api: Api, bad: str
) -> None:
    real = await api.issue(USERNAME)
    decoy = await api.issue(UNKNOWN)

    first = (await api.verify(bad, real), await api.verify(bad, decoy))
    counted = (await api.verify(WRONG, real), await api.verify(WRONG, decoy))
    after = (await api.verify(bad, real), await api.verify(bad, decoy))

    for real_answer, decoy_answer in (first, counted, after):
        assert real_answer.status_code == decoy_answer.status_code == 400
        assert real_answer.json() == decoy_answer.json()
        assert real_answer.headers.get_list("set-cookie") == decoy_answer.headers.get_list("set-cookie")
    assert [pair[1].json()["attemptsLeft"] for pair in (first, counted, after)] == [5, 4, 4]


# Criterion 5
async def test_given_decoys_when_requests_are_counted_then_the_hourly_cap_and_signin_limit_apply_like_real(
    api: Api,
) -> None:
    for name in (UNKNOWN, USERNAME):
        for _ in range(5):
            assert (await api.request_code(name)).status_code == 200
            api.clock.advance(timedelta(seconds=60))
    unknown_sixth = await api.request_code(UNKNOWN)
    known_sixth = await api.request_code(USERNAME)

    assert unknown_sixth.status_code == known_sixth.status_code == 429
    assert unknown_sixth.headers["retry-after"] == known_sixth.headers["retry-after"] == "3000"
    assert api.guard.buckets == ["signin"] * 12
    assert len(api.mailer.sent) == 5


# Criterion 5
async def test_given_a_decoy_when_stored_then_it_has_the_columns_of_a_real_one_and_a_hash_no_code_matches(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await api.issue(UNKNOWN)

    row = await owner.fetchrow("SELECT * FROM web_auth.login_request WHERE id = $1", cookie)

    assert row is not None
    assert row["username_key"].strip() == username_key(b"c" * 32, UNKNOWN)
    assert row["expires_at"] == T0 + timedelta(minutes=10)
    assert row["attempts"] == 0
    assert row["dead_at"] is None
    assert row["sent_at"] == T0  # counted by the hourly cap like a sent code
    stored = bytes.fromhex(row["code_hash"].strip())
    assert not any(hash_code(b"a" * 32, cookie, code) == stored for code in CODES)
    assert not any(hash_code(b"a" * 32, cookie, f"{n:06d}") == stored for n in range(0, 1_000_000, 1009))


# Criterion 5
async def test_given_old_decoys_when_a_later_request_is_stored_then_the_retention_purge_removes_them(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await api.issue(UNKNOWN)
    api.clock.advance(RETENTION - timedelta(seconds=1))
    await api.issue("another-name")
    assert await _rows(owner) == 2
    api.clock.advance(timedelta(seconds=2))

    await api.issue("third-name")

    old = await owner.fetchval(
        "SELECT count(*) FROM web_auth.login_request WHERE username_key = $1", username_key(b"c" * 32, UNKNOWN)
    )
    assert old == 0
    assert await _rows(owner) == 2


# Criterion 5
async def test_given_decoys_up_to_the_open_cap_when_one_more_is_requested_then_it_is_refused_like_a_real_one(
    api: Api,
) -> None:
    for index in range(CAP):
        assert (await api.request_code(f"name-{index}")).status_code == 200

    response = await api.request_code(UNKNOWN)

    assert response.status_code == 429


# Criterion 5
async def test_given_a_second_request_for_an_unknown_name_when_stored_then_the_first_decoy_is_dead(api: Api) -> None:
    first = await api.issue(UNKNOWN)
    api.clock.advance(timedelta(seconds=60))
    second = await api.issue(UNKNOWN)

    old = await api.verify(WRONG, first)
    new = await api.verify(WRONG, second)

    assert "attemptsLeft" not in old.json()
    assert new.json()["attemptsLeft"] == 4


def _within_noise(first: float, second: float) -> bool:
    return abs(first - second) <= max(NOISE_SHARE * max(first, second), NOISE_FLOOR_SECONDS)


async def _timed(action: Callable[[], Awaitable[object]]) -> float:
    start = time.perf_counter()
    await action()
    return time.perf_counter() - start


# Criterion 6
async def test_given_the_two_paths_when_a_code_is_requested_many_times_then_the_medians_are_within_the_bound(
    api: Api,
) -> None:
    known: list[float] = []
    unknown: list[float] = []
    for index in range(SAMPLES + WARM_UP):
        for name, samples in ((USERNAME, known), (UNKNOWN, unknown)):
            api.clock.advance(timedelta(hours=2))
            api.mailer.sent.clear()
            # the answer only; the mail goes out after it (see CodeRequests.deliver)
            elapsed = await _timed(lambda name=name: api.requests.request(name, "client", "request-id"))
            if index >= WARM_UP:
                samples.append(elapsed)

    assert _within_noise(statistics.median(known), statistics.median(unknown)), (known, unknown)


# Criterion 6
async def test_given_the_two_paths_when_a_wrong_code_is_posted_many_times_then_the_medians_are_within_the_bound(
    api: Api,
) -> None:
    known: list[float] = []
    unknown: list[float] = []
    for index in range(SAMPLES + WARM_UP):
        for name, samples in ((USERNAME, known), (UNKNOWN, unknown)):
            api.clock.advance(timedelta(hours=2))
            cookie = await api.issue(name)
            elapsed = await _timed(lambda cookie=cookie: api.verify(WRONG, cookie))
            if index >= WARM_UP:
                samples.append(elapsed)

    assert _within_noise(statistics.median(known), statistics.median(unknown)), (known, unknown)


def test_given_the_noise_bound_when_medians_are_compared_then_a_big_gap_fails_and_a_small_one_passes() -> None:
    assert _within_noise(0.010, 0.014)
    assert _within_noise(0.001, 0.005)
    assert not _within_noise(0.010, 0.030)
    assert not _within_noise(0.001, 0.0061)
