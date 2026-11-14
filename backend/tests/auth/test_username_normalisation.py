# pyright: reportUnusedImport=false
"""U-web-settings-77: the sign-in username ignores surrounding spaces and letter case (D-24), on a real PostgreSQL."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Any

import asyncpg
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient, Response

from app.auth.digest import username_digest
from app.auth.login_requests import LoginRequests
from app.auth.request_code import attach_request_code
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
from tests.fakes import FakeClock, FakeCodes, FakeMailer, make_settings, real_minute

ORIGIN = "https://settings.example.test"
HASH_KEY = b"c" * 32
ADDRESS = "marco@example.test"
CODES = [f"{n:06d}" for n in range(111111, 111111 + 20 * 111111, 111111)]
MARCO_DIGEST = "efb8c7b2ca114cad6f077556e4d28a89"  # username_digest(b"c" * 32, "Marco") as it was before U-77
OWNER_KEY = username_key(HASH_KEY, "marco")


class RecordingGuard:
    async def check(self, bucket: str, request: Request) -> None:
        return None


@dataclass
class Api:
    http: AsyncClient
    mailer: FakeMailer
    store: LoginRequests
    configured: str

    async def request(self, username: object) -> Response:
        return await self.http.post("/auth/request-code", json={"username": username}, headers={"Origin": ORIGIN})

    async def verify(self, code: str, cookie: str) -> Response:
        return await self.http.post(
            "/auth/verify-code", json={"code": code}, headers={"Origin": ORIGIN, "Cookie": f"__Host-login={cookie}"}
        )


@pytest.fixture(params=["marco", "Marco", " MARCO "], ids=["configured-lower", "configured-mixed", "configured-padded"])
async def api(request: pytest.FixtureRequest, web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(real_minute())
    mailer = FakeMailer()
    ids = SecretsIdSource()
    configured: str = request.param
    app = build_app(
        make_settings(username=configured), clock=clock, ids=ids, codes=FakeCodes(list(CODES)), mailer=mailer
    )
    events = SecurityEvents(web_database, clock, b"e" * 32)
    store = LoginRequests(web_database, ids, hash_key=b"a" * 32, ttl=timedelta(seconds=600), max_attempts=5)
    sessions = SessionStore(web_database, ids, events)
    attach_database(app, web_database, clock)
    attach_request_code(app, store, events)
    attach_sessions(app, sessions, events)
    attach_verify_code(app, store, sessions, events)
    app.state.limit_guard = RecordingGuard()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, mailer, store, configured)


def _cookie(response: Response) -> str:
    jar: SimpleCookie = SimpleCookie()
    jar.load(response.headers["set-cookie"])
    return jar["__Host-login"].value


async def _keys(owner: asyncpg.Connection) -> list[str]:  # noqa: F811
    rows = await owner.fetch("SELECT username_key FROM web_auth.login_request ORDER BY created_at")
    return [str(row["username_key"]).strip() for row in rows]


@pytest.mark.parametrize("typed", ["marco", "Marco", " marco ", "MARCO", "\tMarCo\n"])
async def test_given_the_owner_typed_with_other_spacing_or_case_when_requested_then_a_code_goes_to_the_owner_key(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    typed: str,
) -> None:
    response = await api.request(typed)

    assert response.status_code == 200
    assert [sent[0] for sent in api.mailer.sent] == [ADDRESS]
    assert await _keys(owner) == [OWNER_KEY]


async def test_given_all_spellings_when_requested_then_they_all_create_the_same_owner_key(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    for typed in ("marco", "Marco", " marco ", "MARCO"):
        await api.request(typed)

    assert set(await _keys(owner)) == {OWNER_KEY}


async def test_given_a_code_for_a_differently_typed_owner_when_verified_then_the_session_keeps_the_raw_digest(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    response = await api.request("MARCO ")

    verified = await api.verify("111111", _cookie(response))

    assert verified.status_code == 200
    row = await owner.fetchrow("SELECT username_hash FROM web_auth.session")
    assert row is not None
    assert str(row["username_hash"]).strip() == username_digest(HASH_KEY, api.configured)
    if api.configured == "Marco":
        assert str(row["username_hash"]).strip() == MARCO_DIGEST  # the audit actor web:<digest> did not change


async def test_given_an_unknown_name_when_requested_then_the_answer_matches_the_owners_and_it_gets_a_decoy(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    known = await api.request("Marco")
    unknown = await api.request(" Somebody-Else ")

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert sorted(known.headers) == sorted(unknown.headers)
    assert [sent[0] for sent in api.mailer.sent] == [ADDRESS]
    assert await _keys(owner) == [OWNER_KEY, username_key(HASH_KEY, "somebody-else")]


async def test_given_the_email_address_typed_as_username_when_requested_then_it_is_a_decoy_and_no_mail_goes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    response = await api.request(f" {ADDRESS.upper()} ")

    assert response.status_code == 200
    assert api.mailer.sent == []
    assert await _keys(owner) == [username_key(HASH_KEY, ADDRESS)]


async def test_given_a_decoy_and_the_owner_when_requested_then_the_same_steps_run(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    steps: list[str] = []
    for name in ("create", "create_decoy"):
        original = getattr(api.store, name)

        def spy(*args: Any, _original: Callable[..., Awaitable[Any]] = original) -> Awaitable[Any]:
            steps.append("store")
            return _original(*args)

        monkeypatch.setattr(api.store, name, spy)

    await api.request("MARCO")
    owner_steps = list(steps)
    steps.clear()
    await api.request(" nobody ")

    assert steps == owner_steps == ["store"]


@pytest.mark.parametrize("typed", ["", "   ", "\t\n", "\u3000", "bad\nname", "bad\x00name"])
async def test_given_an_empty_or_bad_username_after_trimming_when_requested_then_the_same_422_as_for_empty(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    typed: str,
) -> None:
    response = await api.request(typed)

    assert response.status_code == 422
    assert response.json() == {"type": "about:blank", "title": "Unprocessable content", "status": 422}
    assert await _keys(owner) == []
    assert api.mailer.sent == []
