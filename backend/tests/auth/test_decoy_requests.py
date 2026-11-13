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
from sqlalchemy import text

from app.auth.code_hash import hash_code
from app.auth.login_requests import RETENTION, Applicant, LoginRequest, LoginRequests
from app.auth.request_code import CodeRequests, attach_request_code
from app.auth.request_code_rules import RequestLimits, username_key
from app.auth.session import SessionStore, attach_sessions
from app.auth.verify_code import attach_verify_code
from app.db import Database
from app.errors import RateLimited
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
from tests.step_recorder import StepRecorder, first_difference

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

    async def request_code(self, username: str, *, client: str | None = None, cookie: str | None = None) -> Response:
        # The test peer 127.0.0.1 is a trusted proxy, so X-Forwarded-For names the client (ADR-0034).
        headers = {"Origin": ORIGIN}
        if client is not None:
            headers["X-Forwarded-For"] = client
        if cookie is not None:
            headers["Cookie"] = f"__Host-login={cookie}"
        return await self.http.post(REQUEST_CODE, json={"username": username}, headers=headers)

    async def issue(self, username: str) -> str:
        response = await self.request_code(username)
        assert response.status_code == 200
        return _cookie(response)

    async def verify(self, code: object, cookie: str) -> Response:
        return await self.http.post(
            VERIFY, json={"code": code}, headers={"Origin": ORIGIN, "Cookie": f"__Host-login={cookie}"}
        )


@pytest.fixture
async def api(web_database: Database, request: pytest.FixtureRequest) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    mailer = FakeMailer()
    ids = SecretsIdSource()
    overrides: dict[str, object] = getattr(request, "param", {})
    settings = make_settings(trusted_proxy_cidrs=["127.0.0.1/32"], **overrides)
    app = build_app(settings, clock=clock, ids=ids, codes=FakeCodes(list(CODES)), mailer=mailer)
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
    for _ in range(5):
        for name in (UNKNOWN, USERNAME):
            assert (await api.request_code(name)).status_code == 200
        api.clock.advance(timedelta(seconds=60))
    unknown_sixth = await api.request_code(UNKNOWN)
    known_sixth = await api.request_code(USERNAME)

    assert unknown_sixth.status_code == known_sixth.status_code == 429
    assert unknown_sixth.headers["retry-after"] == known_sixth.headers["retry-after"] == "3300"
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
        assert (await api.request_code(f"name-{index}", client=_client(index))).status_code == 200

    response = await api.request_code(UNKNOWN, client=_client(CAP))

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


def _client(index: int) -> str:
    return f"10.1.{index // 250}.{index % 250 + 1}"


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
            elapsed = await _timed(lambda name=name: api.requests.request(name, "client", "request-id", None))
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


# ---- U-web-settings-53 ---------------------------------------------------------------------------------------------


# Criterion 1 (RT-01, AC-16)
async def test_given_100_open_decoys_from_100_clients_when_the_owner_asks_from_another_client_then_200_and_a_mail(
    api: Api,
) -> None:
    for index in range(CAP):
        assert (await api.request_code(f"name-{index}", client=_client(index))).status_code == 200

    owner_answer = await api.request_code(USERNAME, client="10.9.9.9")
    one_more_decoy = await api.request_code(UNKNOWN, client="10.9.9.8")

    assert owner_answer.status_code == 200
    assert [sent[1] for sent in api.mailer.sent] == ["111111"]
    assert one_more_decoy.status_code == 429  # the decoys have their own cap and it is full
    assert one_more_decoy.headers["retry-after"] == "600"


# Criterion 1 and 2
async def test_given_one_client_when_it_asks_for_many_names_then_it_stops_at_the_per_client_number_not_at_the_cap(
    api: Api,
) -> None:
    for index in range(10):
        assert (await api.request_code(f"name-{index}", client="10.7.7.7")).status_code == 200

    refused = await api.request_code("name-10", client="10.7.7.7")
    owner_answer = await api.request_code(USERNAME, client="10.8.8.8")

    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "600"
    assert owner_answer.status_code == 200
    assert len(api.mailer.sent) == 1


# Criterion 2 (W-7)
@pytest.mark.parametrize("api", [{"login_requests_per_client_per_hour": 3}], indirect=True)
async def test_given_one_client_over_its_hourly_number_when_it_asks_then_429_while_another_client_gets_200(
    api: Api,
) -> None:
    for index in range(3):
        assert (await api.request_code(f"name-{index}", client="10.7.7.7")).status_code == 200
        api.clock.advance(timedelta(minutes=11))  # each request has expired before the next

    refused = await api.request_code("name-3", client="10.7.7.7")
    other = await api.request_code("name-3", client="10.8.8.8")

    assert refused.status_code == 429
    assert refused.headers["retry-after"] == str(60 * 60 - 33 * 60)
    assert other.status_code == 200


# Criterion 3 (RT-04)
async def test_given_the_owners_live_request_in_browser_a_when_another_client_asks_then_the_code_of_a_still_verifies(
    api: Api,
) -> None:
    cookie_a = await api.issue(USERNAME)
    api.clock.advance(timedelta(seconds=60))

    other = await api.request_code(USERNAME, client="10.9.9.9")
    verified = await api.verify("111111", cookie_a)

    assert other.status_code == 200
    assert verified.status_code == 204
    assert [sent[1] for sent in api.mailer.sent] == ["111111", "122222"]


# Criterion 3
async def test_given_the_owners_live_request_when_its_cookie_comes_from_another_client_then_it_is_replaced(
    api: Api,
) -> None:
    cookie_a = await api.issue(USERNAME)
    api.clock.advance(timedelta(seconds=60))

    replacement = await api.request_code(USERNAME, client="10.9.9.9", cookie=cookie_a)
    old = await api.verify("111111", cookie_a)
    new = await api.verify("122222", _cookie(replacement))

    assert replacement.status_code == 200
    assert old.status_code == 400
    assert new.status_code == 204


# Criterion 3
async def test_given_a_live_request_when_the_same_client_asks_again_without_the_cookie_then_it_replaces_it(
    api: Api,
) -> None:
    cookie_a = await api.issue(USERNAME)
    api.clock.advance(timedelta(seconds=60))

    second = await api.issue(USERNAME)

    assert (await api.verify("111111", cookie_a)).status_code == 400
    assert (await api.verify("122222", second)).status_code == 204


# Criterion 3 (the number of live requests of one username is 3)
async def test_given_three_live_requests_of_a_username_when_a_fourth_client_asks_then_429_until_the_oldest_expires(
    api: Api,
) -> None:
    for index in range(3):
        assert (await api.request_code(USERNAME, client=_client(index))).status_code == 200
        api.clock.advance(timedelta(seconds=60))

    refused = await api.request_code(USERNAME, client=_client(3))

    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "420"  # the first of the three expires at T0 + 600, now is T0 + 180
    assert len(api.mailer.sent) == 3


# Criterion 4
async def test_given_a_refused_request_when_the_clock_moves_then_retry_after_follows_the_real_remaining_wait(
    api: Api,
) -> None:
    for index in range(CAP):
        await api.request_code(f"name-{index}", client=_client(index))

    waits: list[tuple[int, str]] = []
    for seconds in (0, 100, 599):
        api.clock.set(T0 + timedelta(seconds=seconds))
        refused = await api.request_code(UNKNOWN, client="10.9.9.8")
        waits.append((refused.status_code, refused.headers["retry-after"]))
    api.clock.set(T0 + timedelta(seconds=600))
    freed = await api.request_code(UNKNOWN, client="10.9.9.8")

    assert waits == [(429, "600"), (429, "500"), (429, "1")]
    assert freed.status_code == 200


# Criterion 5 (AC-30)
@pytest.mark.parametrize("fail", [False, True])
async def test_given_five_requests_then_a_sixth_when_known_and_unknown_then_status_and_retry_after_are_identical(
    api: Api, fail: bool
) -> None:
    if fail:
        api.mailer.fail()
    for _ in range(5):
        for name in (UNKNOWN, USERNAME):
            assert (await api.request_code(name)).status_code == 200
        api.clock.advance(timedelta(seconds=60))

    unknown_sixth = await api.request_code(UNKNOWN)
    known_sixth = await api.request_code(USERNAME)
    api.clock.set(T0 + timedelta(seconds=3599))
    unknown_late = await api.request_code(UNKNOWN)
    known_late = await api.request_code(USERNAME)

    assert unknown_sixth.status_code == known_sixth.status_code == 429
    assert unknown_sixth.headers["retry-after"] == known_sixth.headers["retry-after"] == "3300"
    assert unknown_sixth.json() == known_sixth.json()
    assert unknown_late.status_code == known_late.status_code == 429
    assert unknown_late.headers["retry-after"] == known_late.headers["retry-after"] == "1"
    assert len(api.mailer.sent) == (0 if fail else 5)


# ---- U-web-settings-62 (CR-05): the same steps, recorded, instead of the same time, measured -------------------------


@pytest.fixture
def recorder(api: Api, monkeypatch: pytest.MonkeyPatch) -> StepRecorder:
    recording = StepRecorder()
    recording.attach(monkeypatch, api.mailer)
    return recording


# Criterion 3 (AC-30)
async def test_given_a_known_and_an_unknown_username_when_requested_then_the_recorded_steps_are_equal(
    api: Api, recorder: StepRecorder
) -> None:
    await api.requests.request(USERNAME, "client", "request-1", None)
    known = recorder.take()
    api.clock.advance(timedelta(hours=2))
    await api.requests.request(UNKNOWN, "client", "request-2", None)
    unknown = recorder.take()

    assert first_difference(known, unknown) is None, (known, unknown)
    assert any("INSERT INTO web_auth.login_request" in step for step in known)  # the recorder sees the database
    assert not any(step.startswith("mail") for step in known + unknown)  # the answer never waits for the mail


# Criterion 3 (AC-30)
async def test_given_a_known_and_an_unknown_username_when_refused_by_the_cooldown_then_the_recorded_steps_are_equal(
    api: Api, recorder: StepRecorder
) -> None:
    await api.requests.request(USERNAME, "client", "request-1", None)
    await api.requests.request(UNKNOWN, "client", "request-2", None)
    recorder.take()

    refusals: list[list[str]] = []
    for name in (USERNAME, UNKNOWN):
        with pytest.raises(RateLimited):
            await api.requests.request(name, "client", "request-3", None)
        refusals.append(recorder.take())

    assert first_difference(refusals[0], refusals[1]) is None, refusals
    assert refusals[0]


# Criterion 3 (AC-30)
async def test_given_a_known_and_an_unknown_username_when_a_wrong_code_is_posted_then_the_recorded_steps_are_equal(
    api: Api, recorder: StepRecorder
) -> None:
    real = await api.issue(USERNAME)
    decoy = await api.issue(UNKNOWN)
    recorder.take()

    await api.verify(WRONG, real)
    known = recorder.take()
    await api.verify(WRONG, decoy)
    unknown = recorder.take()

    assert first_difference(known, unknown) is None, (known, unknown)
    assert any("UPDATE web_auth.login_request SET attempts" in step for step in known)


# Criterion 3 (AC-30): the mail is the one difference, and it comes after the answer
async def test_given_a_known_and_an_unknown_username_when_the_answer_is_given_then_only_the_known_one_is_mailed_after(
    api: Api, recorder: StepRecorder
) -> None:
    known = await api.requests.request(USERNAME, "client", "request-1", None)
    unknown = await api.requests.request(UNKNOWN, "client", "request-2", None)
    recorder.take()

    assert unknown.delivery is None
    assert known.delivery is not None
    await api.requests.deliver(known.delivery)

    assert [step for step in recorder.take() if step.startswith("mail")] == ["mail: send_code"]


# Criterion 3: a recorder that cannot tell paths apart proves nothing, so a deliberately different fake must show
async def test_given_a_store_that_does_an_extra_query_for_unknown_names_when_recorded_then_the_difference_is_found(
    api: Api,
    recorder: StepRecorder,
    monkeypatch: pytest.MonkeyPatch,
    web_database: Database,  # noqa: F811
) -> None:
    original = LoginRequests.create_decoy

    async def leaky(_self: LoginRequests, who: Applicant, now: datetime, limits: RequestLimits) -> LoginRequest:
        async with web_database.session() as session:
            await session.execute(text("SELECT 1 FROM web_auth.session"))
        return await original(_self, who, now, limits)

    await api.requests.request(USERNAME, "client", "request-1", None)
    known = recorder.take()
    api.clock.advance(timedelta(hours=2))
    monkeypatch.setattr(LoginRequests, "create_decoy", leaky)
    await api.requests.request(UNKNOWN, "client", "request-2", None)
    unknown = recorder.take()

    difference = first_difference(known, unknown)
    assert difference is not None
    assert "web_auth.session" in difference


def test_given_equal_and_different_step_lists_when_compared_then_only_the_different_ones_report() -> None:
    assert first_difference(["a", "b"], ["a", "b"]) is None
    assert first_difference(["a", "b"], ["a", "c"]) == "step 2: 'b' against 'c'"
    assert first_difference(["a"], ["a", "b"]) == "step 2: nothing against 'b'"
    assert first_difference(["a", "b"], ["a"]) == "step 2: 'b' against nothing"
