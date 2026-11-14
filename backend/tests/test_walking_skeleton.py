# pyright: reportUnusedImport=false
"""U-web-settings-25: the first path through the real app, in process, with fakes and a real PostgreSQL.

request code -> read it from the FakeMailer -> verify -> GET /api/session -> GET /api/settings ->
PUT /api/settings -> logout. It keeps one working end-to-end path while later units add to it.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.auth.cookies import COOKIE_NAME
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
    agent,
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
USERNAME = "canary-user"  # the canary values of tests/conftest.py: any log line that holds one fails the test
CODE = "424242"
WRONG = "111111"
ZONE = "Pacific/Kiritimati"
CHANGE = {
    "timeZone": ZONE,
    "quietStart": "22:30",
    "quietEnd": "06:45",
    "overviewAt": "18:05",
    "remindAt": "09:15",
}
DEFAULTS = {
    "timeZone": "Europe/Amsterdam",
    "quietStart": "23:00",
    "quietEnd": "07:00",
    "overviewAt": "18:00",
    "remindAt": "09:00",
}
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}


@dataclass
class Walk:
    http: AsyncClient
    mailer: FakeMailer

    async def request_code(self) -> str:
        """Ask for a code as the allowed user; return the login cookie value."""
        response = await self.http.post("/auth/request-code", json={"username": USERNAME}, headers={"Origin": ORIGIN})
        assert response.status_code == 200
        return _cookie(response, "__Host-login")

    async def verify(self, code: str, login: str) -> Response:
        return await self.http.post(
            "/auth/verify-code", json={"code": code}, headers={"Origin": ORIGIN, "Cookie": f"__Host-login={login}"}
        )

    async def sign_in(self) -> str:
        """Run request-code and verify-code with the code read from the mailer; return the session cookie value."""
        login = await self.request_code()
        response = await self.verify(self.mailer.sent[-1][1], login)
        assert response.status_code == 204
        return _cookie(response, COOKIE_NAME)


def _cookie(response: Response, name: str) -> str:
    for header in response.headers.get_list("set-cookie"):
        jar: SimpleCookie = SimpleCookie()
        jar.load(header)
        if name in jar:
            return jar[name].value
    raise AssertionError(f"no {name} cookie was set")


@pytest.fixture
async def walk(web_database: Database) -> AsyncIterator[Walk]:  # noqa: F811
    clock = FakeClock(T0)
    ids = SecretsIdSource()
    mailer = FakeMailer()
    settings = make_settings(username=USERNAME)
    app = build_app(settings, clock=clock, ids=ids, codes=FakeCodes([CODE]), mailer=mailer)
    events = SecurityEvents(web_database, clock, b"e" * 32)
    logins = LoginRequests(web_database, ids, hash_key=b"a" * 32, ttl=timedelta(seconds=600), max_attempts=5)
    sessions = SessionStore(web_database, ids, events)
    attach_database(app, web_database, clock)
    attach_request_code(app, logins, events)
    attach_sessions(app, sessions, events)
    attach_verify_code(app, logins, sessions, events)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Walk(http, mailer)


async def _session(walk: Walk, cookie: str) -> Response:
    return await walk.http.get("/api/session", cookies={COOKIE_NAME: cookie})


# Criterion 1
async def test_given_a_fresh_database_when_the_allowed_user_signs_in_then_the_session_has_the_masked_address(
    walk: Walk,
) -> None:
    cookie = await walk.sign_in()

    response = await _session(walk, cookie)

    assert response.status_code == 200
    body = response.json()
    assert body["maskedAddress"] == "m***@example.test"
    assert body["csrfToken"]
    assert walk.mailer.sent[0][0] == "marco@example.test"


# Criterion 2
async def test_given_the_session_when_settings_are_read_then_changed_then_version_0_becomes_1_with_a_web_audit_record(
    walk: Walk,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await walk.sign_in()
    token = (await _session(walk, cookie)).json()["csrfToken"]

    before = await walk.http.get("/api/settings", cookies={COOKIE_NAME: cookie})
    saved = await walk.http.put(
        "/api/settings",
        json={"values": CHANGE, "version": 0},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
        cookies={COOKIE_NAME: cookie},
    )

    assert before.status_code == 200
    assert (before.json()["version"], before.json()["values"]) == (0, DEFAULTS)
    assert saved.status_code == 200
    assert (saved.json()["version"], saved.json()["values"], saved.json()["updatedVia"]) == (1, CHANGE, "web")
    audit = await owner.fetch("select via, old, new from settings.settings_change")
    assert [r["via"] for r in audit] == ["web"]


async def _change(walk: Walk, cookie: str, token: str) -> Response:
    return await walk.http.put(
        "/api/settings",
        json={"values": CHANGE, "version": 0},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
        cookies={COOKIE_NAME: cookie},
    )


# Criterion 3
async def test_given_a_wrong_code_once_when_the_right_code_follows_on_the_same_request_then_it_signs_in(
    walk: Walk,
) -> None:
    login = await walk.request_code()

    refused = await walk.verify(WRONG, login)
    accepted = await walk.verify(walk.mailer.sent[-1][1], login)

    assert refused.status_code == 400
    assert refused.json()["attemptsLeft"] == 4  # attempt 1 of 5 is used; the next one is attempt 2
    assert accepted.status_code == 204
    assert _cookie(accepted, COOKIE_NAME)


# Criterion 4
async def test_given_the_saved_row_when_read_as_the_agent_role_then_the_agent_sees_the_new_values(
    walk: Walk,
    agent: asyncpg.Connection,  # noqa: F811
) -> None:
    cookie = await walk.sign_in()
    token = (await _session(walk, cookie)).json()["csrfToken"]

    assert (await _change(walk, cookie, token)).status_code == 200

    row = await agent.fetchrow(
        "select zone, quiet_start, quiet_end, overview_at, remind_at, version from settings.schedule"
    )
    assert row is not None
    assert row["zone"] == ZONE
    assert (row["quiet_start"], row["quiet_end"]) == (22 * 60 + 30, 6 * 60 + 45)
    assert (row["overview_at"], row["remind_at"], row["version"]) == (18 * 60 + 5, 9 * 60 + 15, 1)


# Criterion 5
async def test_given_a_logout_when_the_old_cookie_is_used_then_401_everywhere(walk: Walk) -> None:
    cookie = await walk.sign_in()
    token = (await _session(walk, cookie)).json()["csrfToken"]

    out = await walk.http.post(
        "/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": token}, cookies={COOKIE_NAME: cookie}
    )

    assert out.status_code == 204
    assert (await _session(walk, cookie)).status_code == 401
    assert (await walk.http.get("/api/settings", cookies={COOKIE_NAME: cookie})).status_code == 401
    assert (await _change(walk, cookie, token)).status_code == 401
    assert (await _session(walk, cookie)).json() == GENERIC_401


# Criterion 6
async def test_given_the_whole_path_when_logs_are_captured_then_no_canary_code_username_cookie_or_zone_appears(
    walk: Walk,
    canary_log_records: list[logging.LogRecord],
) -> None:
    login = await walk.request_code()
    await walk.verify(WRONG, login)
    accepted = await walk.verify(walk.mailer.sent[-1][1], login)
    cookie = _cookie(accepted, COOKIE_NAME)
    token = (await _session(walk, cookie)).json()["csrfToken"]
    await walk.http.get("/api/settings", cookies={COOKIE_NAME: cookie})
    await _change(walk, cookie, token)
    await walk.http.post(
        "/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": token}, cookies={COOKIE_NAME: cookie}
    )

    formatter = logging.Formatter()
    text = " | ".join(formatter.format(record) for record in canary_log_records)
    assert canary_log_records
    for secret in (USERNAME, CODE, WRONG, ZONE, cookie, login, token):
        assert secret not in text
