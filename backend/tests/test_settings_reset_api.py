# pyright: reportUnusedImport=false
"""U-web-settings-45 (R2): POST /api/settings/reset writes the defaults through the same repository as the PUT."""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.auth.cookies import COOKIE_NAME
from app.auth.csrf import csrf_token
from app.auth.digest import username_digest
from app.auth.session import SessionStore, attach_sessions
from app.core.security import ROUTE_ALLOW_LIST, inventory_violations
from app.db import Database
from app.errors import ProblemError
from app.export_openapi import DEFAULT_TARGET
from app.ids import SecretsIdSource
from app.main import discover_routers
from app.security_events import SecurityEvents
from app.settings_repo import SettingsRepository
from app.startup import attach_database
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.fakes import FakeClock, make_app, make_settings, real_minute

CSRF_KEY = b"b" * 32
ORIGIN = "https://settings.example.test"
USER = username_digest(b"k" * 32, "canary-user")
OTHER = "a" * 32
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}
GENERIC_403 = {"type": "about:blank", "title": "Forbidden", "status": 403}
GENERIC_500 = {"type": "about:blank", "title": "Internal server error", "status": 500}
DEFAULTS = {
    "timeZone": "Europe/Amsterdam",
    "quietStart": "23:00",
    "quietEnd": "07:00",
    "overviewAt": "18:00",
    "remindAt": "09:00",
}
CHANGED = TimePolicy("Pacific/Kiritimati", time(22, 30), time(6, 45), time(18, 5), time(9, 15))
URL = "/api/settings/reset"
VERSION = "select version from settings.schedule"
AUDITS = "select count(*) from settings.settings_change"


class RefusingGuard:
    """A stand-in for the limit guard: refuses every request with 413 and remembers the bucket."""

    def __init__(self) -> None:
        self.buckets: list[str] = []

    async def check(self, bucket: str, request: Request) -> None:
        self.buckets.append(bucket)
        raise ProblemError(413)


@dataclass
class Api:
    http: AsyncClient
    app: FastAPI
    store: SessionStore
    t0: datetime


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    t0 = real_minute()  # the database windows the security events by its own minute
    clock = FakeClock(t0)
    store = SessionStore(web_database, SecretsIdSource(), SecurityEvents(web_database, clock, b"e" * 32))
    app = make_app(make_settings())
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, SecurityEvents(web_database, clock, b"e" * 32))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, app, store, t0)


async def _post(api: Api, body: Any, *, token: bool = True, origin: str | None = ORIGIN) -> Any:
    """Send the reset as the signed-in user; the switches leave out one part of the request."""
    value, created = await api.store.create(USER, api.t0)
    headers: dict[str, str] = {}
    if token:
        headers["X-CSRF-Token"] = csrf_token(CSRF_KEY, created.id_hash)
    if origin is not None:
        headers["Origin"] = origin
    return await api.http.post(URL, json=body, headers=headers, cookies={COOKIE_NAME: value})


async def _store_changed(api: Api) -> None:
    """Leave a changed row at version 2, written by another actor."""
    repository = SettingsRepository(api.app.state.database)
    await repository.write(DEFAULT_POLICY, 0, OTHER)
    await repository.write(CHANGED, 1, OTHER)


# Criterion 1
async def test_given_a_changed_row_when_reset_at_the_current_version_then_the_defaults_are_stored_and_returned(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _store_changed(api)

    response = await _post(api, {"version": 2})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"values", "version", "updatedAt", "updatedVia"}
    assert body["values"] == DEFAULTS
    assert (body["version"], body["updatedVia"]) == (3, "web")
    stored = await SettingsRepository(api.app.state.database).read()
    assert (stored.version, stored.policy) == (3, DEFAULT_POLICY)
    assert await owner.fetchval("select zone from settings.schedule") == "Europe/Amsterdam"


async def test_given_no_row_yet_when_reset_at_version_0_then_the_defaults_are_stored_at_version_1(api: Api) -> None:
    response = await _post(api, {"version": 0})

    assert response.status_code == 200
    assert (response.json()["version"], response.json()["values"]) == (1, DEFAULTS)


async def test_given_a_reset_when_sent_then_it_counts_against_the_api_bucket(api: Api) -> None:
    guard = RefusingGuard()
    api.app.state.limit_guard = guard

    await _post(api, {"version": 0})

    assert guard.buckets == ["api"]


# Criterion 2
async def test_given_the_reset_when_the_audit_is_read_then_one_web_record_with_the_digest_actor_exists(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _store_changed(api)
    before = await owner.fetchval(AUDITS)

    await _post(api, {"version": 2})

    last = await owner.fetchrow(
        "select via, by from settings.settings_change order by at desc, (new->>'version')::int desc limit 1"
    )
    assert last is not None
    assert await owner.fetchval(AUDITS) == before + 1
    assert (last["via"], last["by"]) == ("web", f"web:{USER}")
    assert re.fullmatch(r"web:[0-9a-f]{32}", last["by"])


# Criterion 3
async def test_given_an_old_version_when_reset_then_409_with_the_current_settings_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _store_changed(api)
    audits = await owner.fetchval(AUDITS)

    response = await _post(api, {"version": 1})

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert set(body) == {"type", "title", "status", "current"}
    assert (body["title"], body["status"]) == ("Conflict", 409)
    assert body["current"]["version"] == 2
    assert body["current"]["values"]["timeZone"] == "Pacific/Kiritimati"
    assert await owner.fetchval("select zone from settings.schedule") == "Pacific/Kiritimati"
    assert await owner.fetchval(AUDITS) == audits


@pytest.mark.parametrize(
    "body",
    [{}, {"version": -1}, {"version": 1.5}, {"version": 2, "values": DEFAULTS}, {"version": 2, "zone": "UTC"}],
)
async def test_given_a_malformed_body_when_reset_then_422_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    body: dict[str, Any],
) -> None:
    await _store_changed(api)

    response = await _post(api, body)

    assert response.status_code == 422
    assert await owner.fetchval(VERSION) == 2


async def test_given_a_non_json_content_type_when_reset_then_415_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _store_changed(api)
    value, created = await api.store.create(USER, api.t0)

    sent = await api.http.post(
        URL,
        content='{"version": 2}',
        headers={"Content-Type": "text/plain", "Origin": ORIGIN, "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash)},
        cookies={COOKIE_NAME: value},
    )

    assert sent.status_code == 415
    assert await owner.fetchval(VERSION) == 2


# Criterion 4
@pytest.mark.parametrize(
    ("token", "origin"),
    [(False, ORIGIN), (True, None), (True, "https://evil.example.test"), (False, None)],
)
async def test_given_no_token_or_a_wrong_origin_when_reset_then_403_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    token: bool,
    origin: str | None,
) -> None:
    await _store_changed(api)

    response = await _post(api, {"version": 2}, token=token, origin=origin)

    assert response.status_code == 403
    assert response.json() == GENERIC_403
    assert await owner.fetchval(VERSION) == 2


async def test_given_no_session_when_reset_then_401_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _store_changed(api)

    response = await api.http.post(URL, json={"version": 2}, headers={"Origin": ORIGIN})

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert await owner.fetchval(VERSION) == 2


async def test_given_a_cross_site_request_when_reset_then_403(api: Api) -> None:
    value, created = await api.store.create(USER, api.t0)

    response = await api.http.post(
        URL,
        json={"version": 0},
        headers={
            "Origin": ORIGIN,
            "Sec-Fetch-Site": "cross-site",
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
        },
        cookies={COOKIE_NAME: value},
    )

    assert response.status_code == 403


async def test_given_a_locked_web_when_reset_then_401_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _store_changed(api)
    value, created = await api.store.create(USER, api.t0)
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", api.t0)

    response = await api.http.post(
        URL,
        json={"version": 2},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash)},
        cookies={COOKIE_NAME: value},
    )

    assert response.status_code == 401
    assert await owner.fetchval(VERSION) == 2


async def test_given_a_failing_audit_when_reset_then_a_generic_500_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _store_changed(api)
    await owner.execute(
        "CREATE OR REPLACE FUNCTION settings.settings_audit() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'audit down'; END $$"
    )

    response = await _post(api, {"version": 2})

    assert response.status_code == 500
    assert response.json() == GENERIC_500
    assert await owner.fetchval("select zone from settings.schedule") == "Pacific/Kiritimati"


# Criterion 5
async def test_given_a_get_on_the_reset_route_when_sent_then_405(api: Api) -> None:
    value, _ = await api.store.create(USER, api.t0)

    response = await api.http.get(URL, cookies={COOKIE_NAME: value})

    assert response.status_code == 405


# Criterion 6 (the agent side is in agents/mail-triage/tests/db/test_web_notice.py)
async def test_given_the_reset_when_the_audit_is_read_then_it_is_a_web_change_by_the_web_role_with_the_defaults(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _store_changed(api)

    await _post(api, {"version": 2})

    row = await owner.fetchrow(
        "select via, db_role, old, new from settings.settings_change order by (new->>'version')::int desc"
    )
    assert row is not None
    assert (row["via"], row["db_role"]) == ("web", "web_settings_runtime")
    old, new = (json.loads(row[key]) if isinstance(row[key], str) else row[key] for key in ("old", "new"))
    assert old["zone"] == "Pacific/Kiritimati"
    assert (new["zone"], new["version"]) == ("Europe/Amsterdam", 3)


# Criterion 7
def _routes() -> list[tuple[str, APIRoute]]:
    return [
        (mounted.prefix + route.path, route)
        for mounted in discover_routers()
        for route in mounted.router.routes
        if isinstance(route, APIRoute)
    ]


def test_given_the_route_inventory_when_read_then_the_reset_path_is_on_the_allow_list_with_the_markers() -> None:
    routes = _routes()
    resets = [route for path, route in routes if path == URL]

    assert URL in ROUTE_ALLOW_LIST
    assert [route.methods for route in resets] == [{"POST"}]
    assert inventory_violations(routes) == []


def test_given_the_openapi_when_read_then_the_reset_route_is_listed_with_its_answers() -> None:
    document = json.loads(DEFAULT_TARGET.read_text(encoding="utf-8"))
    post = document["paths"][URL]["post"]

    assert list(document["paths"][URL]) == ["post"]
    assert {"200", "401", "403", "409", "415", "422", "429", "500"} <= set(post["responses"])
    assert post["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SettingsReset"
    }
    assert document["components"]["schemas"]["SettingsReset"]["additionalProperties"] is False
