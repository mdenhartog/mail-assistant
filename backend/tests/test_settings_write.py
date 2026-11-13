# pyright: reportUnusedImport=false
"""U-web-settings-22: PUT /api/settings and the glue between the request and the shared validation."""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.auth.csrf import csrf_token
from app.auth.digest import username_digest
from app.auth.session import COOKIE_NAME, SessionStore, attach_sessions
from app.core.security import inventory_violations
from app.db import Database
from app.errors import ProblemError
from app.export_openapi import DEFAULT_TARGET
from app.ids import SecretsIdSource
from app.main import discover_routers
from app.security_events import SecurityEvents
from app.settings_models import SettingsValues
from app.settings_repo import SettingsRepository
from app.settings_write import field_problems, to_policy
from app.startup import attach_database
from schedule_policy.policy import DEFAULT_POLICY, Problem, TimePolicy, validate
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.fakes import FakeClock, make_app, make_settings

T0 = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)
CSRF_KEY = b"b" * 32
ORIGIN = "https://settings.example.test"
USER = username_digest(b"k" * 32, "canary-user")
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}
GENERIC_403 = {"type": "about:blank", "title": "Forbidden", "status": 403}
GENERIC_500 = {"type": "about:blank", "title": "Internal server error", "status": 500}
NEW_YORK = {
    "timeZone": "America/New_York",
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
BREAK_AUDIT = (
    "CREATE OR REPLACE FUNCTION settings.settings_audit() RETURNS trigger LANGUAGE plpgsql AS "
    "$$ BEGIN RAISE EXCEPTION 'audit down'; END $$"
)
COUNT = "select count(*) from settings.schedule"


class RefusingGuard:
    """A stand-in for the body limit of U-24: refuses every request with 413."""

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


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
async def api(web_database: Database, clock: FakeClock) -> AsyncIterator[Api]:  # noqa: F811
    store = SessionStore(web_database, SecretsIdSource(), SecurityEvents(web_database, clock, b"e" * 32))
    app = make_app(make_settings())
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, SecurityEvents(web_database, clock, b"e" * 32))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, app, store)


async def _put(
    api: Api, body: Any, *, cookie: bool = True, token: bool = True, origin: str | None = ORIGIN, **extra: Any
) -> Any:
    """Send a PUT as the signed-in user; the switches leave out one part of the request."""
    value, created = await api.store.create(USER, T0)
    headers: dict[str, str] = {}
    if token:
        headers["X-CSRF-Token"] = csrf_token(CSRF_KEY, created.id_hash)
    if origin is not None:
        headers["Origin"] = origin
    return await api.http.put(
        "/api/settings", json=body, headers=headers, cookies={COOKIE_NAME: value} if cookie else {}, **extra
    )


def _update(values: dict[str, Any], version: int = 0) -> dict[str, Any]:
    return {"values": values, "version": version}


async def _rows(owner: asyncpg.Connection) -> int:  # noqa: F811
    return await owner.fetchval(COUNT)


# Criterion 1
async def test_given_a_valid_put_at_the_current_version_when_sent_then_200_with_the_new_settings_and_version(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    first = await _put(api, _update(NEW_YORK))
    second = await _put(api, _update({**NEW_YORK, "timeZone": "Europe/Paris"}, version=1))

    assert first.status_code == 200
    assert first.json()["values"] == NEW_YORK
    assert first.json()["version"] == 1
    assert first.json()["updatedVia"] == "web"
    assert set(first.json()) == {"values", "version", "updatedAt", "updatedVia"}
    assert second.status_code == 200
    assert (second.json()["version"], second.json()["values"]["timeZone"]) == (2, "Europe/Paris")
    stored = await SettingsRepository(api.app.state.database).read()
    assert (stored.version, stored.policy.zone) == (2, "Europe/Paris")
    audit = await owner.fetch("select via, by from settings.settings_change order by (new->>'version')::int")
    assert [(r["via"], r["by"]) for r in audit] == [("web", f"web:{USER}")] * 2


async def test_given_a_put_when_sent_then_it_counts_against_the_api_bucket(api: Api) -> None:
    guard = RefusingGuard()
    api.app.state.limit_guard = guard

    await _put(api, _update(NEW_YORK))

    assert guard.buckets == ["api"]


# Criterion 2
async def test_given_an_overview_inside_the_quiet_hours_when_put_then_422_with_the_rule_value_and_example(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    body = _update({**DEFAULTS, "overviewAt": "23:30"})
    expected = validate(TimePolicy("Europe/Amsterdam", time(23), time(7), time(23, 30), time(9)))

    response = await _put(api, body)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Unprocessable content",
        "status": 422,
        "problems": [
            {"field": "overviewAt", "rule": expected[0].rule, "value": "23:30", "example": expected[0].example}
        ],
    }
    assert expected[0].rule == "overview_in_quiet_hours"
    assert await _rows(owner) == 0


async def test_given_two_broken_rules_when_put_then_every_problem_is_listed_with_its_field(api: Api) -> None:
    body = _update({**DEFAULTS, "timeZone": "Mars/Olympus", "remindAt": "07:00", "quietEnd": "23:30"})

    response = await _put(api, body)

    assert response.status_code == 422
    fields = sorted((p["field"], p["rule"]) for p in response.json()["problems"])
    assert ("timeZone", "zone_unknown") in fields
    assert ("quietEnd", "quiet_window_length") in fields


# Criterion 3
@pytest.mark.parametrize(
    "patch",
    [
        {"overviewAt": "7pm"},
        {"quietStart": "24:00"},
        {"remindAt": "07:00:30"},
        {"quietEnd": 700},
        {"overviewAt": None},
        {"timeZone": "Mars/Olympus"},
        {"timeZone": "../etc/passwd"},
        {"timeZone": "Europe/Amsterdam" + "x" * 64},
        {"timeZone": ""},
        {"timeZone": "UTC\x00"},
    ],
)
async def test_given_a_malformed_value_when_put_then_422_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    patch: dict[str, Any],
) -> None:
    response = await _put(api, _update({**DEFAULTS, **patch}))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert await _rows(owner) == 0
    assert await owner.fetchval("select count(*) from settings.settings_change") == 0


async def test_given_an_unknown_zone_when_put_then_the_problem_names_the_zone_field(api: Api) -> None:
    response = await _put(api, _update({**DEFAULTS, "timeZone": "Mars/Olympus"}))

    assert response.json()["problems"] == [
        {"field": "timeZone", "rule": "zone_unknown", "value": "Mars/Olympus", "example": "Try Europe/Amsterdam"}
    ]


# Criterion 4
async def test_given_an_old_version_when_put_then_409_with_the_current_settings_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await SettingsRepository(api.app.state.database).write(DEFAULT_POLICY, 0, USER)

    response = await _put(api, _update(NEW_YORK, version=0))

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "about:blank"
    assert (body["title"], body["status"]) == ("Conflict", 409)
    assert set(body) == {"type", "title", "status", "current"}
    assert body["current"]["values"] == DEFAULTS
    assert body["current"]["version"] == 1
    assert set(body["current"]) == {"values", "version", "updatedAt", "updatedVia"}
    assert await owner.fetchval("select zone from settings.schedule") == "Europe/Amsterdam"
    assert await owner.fetchval("select count(*) from settings.settings_change") == 1


async def test_given_a_future_version_when_put_then_409(api: Api) -> None:
    response = await _put(api, _update(NEW_YORK, version=7))

    assert response.status_code == 409
    assert response.json()["current"]["version"] == 0


# Criterion 5
async def test_given_an_extra_property_when_put_then_422_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    top = await _put(api, {**_update(NEW_YORK), "updatedBy": "web:x"})
    inner = await _put(api, _update({**NEW_YORK, "locale": "nl"}))

    assert (top.status_code, inner.status_code) == (422, 422)
    assert await _rows(owner) == 0


async def test_given_a_missing_value_when_put_then_422(api: Api) -> None:
    values = {k: v for k, v in NEW_YORK.items() if k != "remindAt"}

    assert (await _put(api, _update(values))).status_code == 422
    assert (await _put(api, {"values": NEW_YORK})).status_code == 422
    assert (await _put(api, _update(NEW_YORK, version=-1))).status_code == 422


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "application/xml"])
async def test_given_a_non_json_content_type_when_put_then_415_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    content_type: str,
) -> None:
    value, created = await api.store.create(USER, T0)
    sent = await api.http.put(
        "/api/settings",
        content=json.dumps(_update(NEW_YORK)),
        headers={
            "Content-Type": content_type,
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
        },
        cookies={COOKIE_NAME: value},
    )

    assert sent.status_code == 415
    assert sent.json() == {"type": "about:blank", "title": "Unsupported media type", "status": 415}
    assert await _rows(owner) == 0


# Criterion 6
async def test_given_a_script_zone_when_put_then_422_and_it_is_only_a_json_string(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    zone = "<script>alert(1)</script>"

    response = await _put(api, _update({**DEFAULTS, "timeZone": zone}))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert json.loads(response.text)["problems"][0]["value"] == zone
    assert await _rows(owner) == 0


# Criterion 7
async def test_given_no_session_when_put_then_401_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    response = await api.http.put("/api/settings", json=_update(NEW_YORK), headers={"Origin": ORIGIN})

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert await _rows(owner) == 0


@pytest.mark.parametrize(
    ("token", "origin"),
    [(False, ORIGIN), (True, None), (True, "https://evil.example.test"), (False, None)],
)
async def test_given_a_session_without_the_token_or_with_a_wrong_origin_when_put_then_403_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    token: bool,
    origin: str | None,
) -> None:
    response = await _put(api, _update(NEW_YORK), token=token, origin=origin)

    assert response.status_code == 403
    assert response.json() == GENERIC_403
    assert await _rows(owner) == 0


async def test_given_a_cross_site_request_when_put_then_403(api: Api) -> None:
    value, created = await api.store.create(USER, T0)

    response = await api.http.put(
        "/api/settings",
        json=_update(NEW_YORK),
        headers={
            "Origin": ORIGIN,
            "Sec-Fetch-Site": "cross-site",
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
        },
        cookies={COOKIE_NAME: value},
    )

    assert response.status_code == 403
    assert response.json() == GENERIC_403


async def test_given_a_locked_web_when_put_then_401_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    value, created = await api.store.create(USER, T0)
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", T0)

    response = await api.http.put(
        "/api/settings",
        json=_update(NEW_YORK),
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash)},
        cookies={COOKIE_NAME: value},
    )

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert await _rows(owner) == 0


# Criterion 8
async def test_given_a_guard_that_refuses_when_put_then_the_request_never_reaches_validation_or_the_store(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api.app.state.limit_guard = RefusingGuard()
    reached: list[int] = []
    original = SettingsRepository.write

    async def spy(self: SettingsRepository, policy: TimePolicy, expected: int, by: str) -> Any:
        reached.append(1)
        return await original(self, policy, expected, by)

    monkeypatch.setattr(SettingsRepository, "write", spy)

    response = await _put(api, _update(NEW_YORK))

    assert response.status_code == 413
    assert reached == []
    assert await _rows(owner) == 0


# Criterion 9
async def test_given_a_failing_audit_trigger_when_put_then_a_generic_500_nothing_is_stored_and_no_zone_is_logged(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    await SettingsRepository(api.app.state.database).write(DEFAULT_POLICY, 0, USER)
    await owner.execute(BREAK_AUDIT)
    caplog.set_level(logging.DEBUG)

    response = await _put(api, _update({**NEW_YORK, "timeZone": "Pacific/Kiritimati"}, version=1))

    assert response.status_code == 500
    assert response.json() == GENERIC_500
    assert await owner.fetchval("select zone from settings.schedule") == "Europe/Amsterdam"
    assert "Kiritimati" not in caplog.text
    assert "audit down" not in response.text


# Criterion 10
def _document() -> dict[str, Any]:
    return json.loads(DEFAULT_TARGET.read_text(encoding="utf-8"))


def test_given_the_openapi_when_read_then_put_settings_is_listed_with_its_answers_and_no_reset_route() -> None:
    document = _document()
    put = document["paths"]["/api/settings"]["put"]

    assert "/api/settings/reset" not in document["paths"]
    assert {"200", "401", "403", "409", "415", "422", "429", "500"} <= set(put["responses"])
    assert put["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SettingsUpdate"
    }
    assert put["responses"]["422"]["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/Problem422"
    }
    assert put["responses"]["409"]["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/Conflict409"
    }


def test_given_the_routes_when_inspected_then_put_settings_declares_session_and_csrf_and_the_inventory_holds() -> None:
    routes = [
        (mounted.prefix + route.path, route)
        for mounted in discover_routers()
        for route in mounted.router.routes
        if isinstance(route, APIRoute)
    ]
    puts = [route for path, route in routes if path == "/api/settings" and "PUT" in (route.methods or set())]

    assert len(puts) == 1
    assert inventory_violations(routes) == []


def test_given_the_app_when_built_then_the_write_schemas_come_from_the_route_not_from_a_hook() -> None:
    import app.settings_models as models  # noqa: PLC0415

    assert not hasattr(models, "declare_write_schemas")


# The glue
def _values(**patch: str) -> SettingsValues:
    return SettingsValues.model_validate({**DEFAULTS, **patch})


def test_given_hhmm_strings_when_converted_then_the_policy_has_naive_whole_minute_times() -> None:
    policy = to_policy(_values(timeZone="America/New_York", quietStart="22:30", quietEnd="06:45", overviewAt="18:05"))

    assert policy == TimePolicy("America/New_York", time(22, 30), time(6, 45), time(18, 5), time(9, 0))
    assert all(t.tzinfo is None for t in (policy.quiet_start, policy.quiet_end, policy.overview_at, policy.remind_at))


def test_given_midnight_and_the_last_minute_when_converted_then_they_are_kept() -> None:
    policy = to_policy(_values(quietStart="00:00", quietEnd="12:00", overviewAt="23:59", remindAt="12:00"))

    assert (policy.quiet_start, policy.overview_at) == (time(0, 0), time(23, 59))


def test_given_a_window_problem_when_mapped_then_one_item_per_window_field_with_the_same_text() -> None:
    items = field_problems(_values(), [Problem("quiet_window_empty", "07:00 to 07:00", "Try 07:00 to 19:00")])

    assert [(i.field, i.rule, i.value, i.example) for i in items] == [
        ("quietStart", "quiet_window_empty", "07:00 to 07:00", "Try 07:00 to 19:00"),
        ("quietEnd", "quiet_window_empty", "07:00 to 07:00", "Try 07:00 to 19:00"),
    ]


def test_given_single_field_rules_when_mapped_then_each_names_its_field() -> None:
    items = field_problems(
        _values(),
        [
            Problem("zone_unknown", "Mars", "Try Europe/Amsterdam"),
            Problem("overview_in_quiet_hours", "23:30", "Try 07:00"),
            Problem("remind_in_quiet_hours", "06:00", "Try 07:00"),
        ],
    )

    assert [(i.field, i.rule) for i in items] == [
        ("timeZone", "zone_unknown"),
        ("overviewAt", "overview_in_quiet_hours"),
        ("remindAt", "remind_in_quiet_hours"),
    ]


def test_given_a_time_rule_when_mapped_then_the_field_holding_the_value_is_named() -> None:
    values = _values(quietEnd="06:30", remindAt="09:15")

    items = field_problems(
        values, [Problem("time_not_whole_minute", "09:15", "Try 09:15"), Problem("time_has_zone", "06:30", "Try 06:30")]
    )

    assert [(i.field, i.rule) for i in items] == [("remindAt", "time_not_whole_minute"), ("quietEnd", "time_has_zone")]


def test_given_a_time_rule_with_an_unmatched_value_when_mapped_then_the_first_time_field_is_named() -> None:
    items = field_problems(_values(), [Problem("time_has_zone", "03:33", "Try 03:33")])

    assert [i.field for i in items] == ["quietStart"]


def test_given_no_problems_when_mapped_then_the_list_is_empty() -> None:
    assert field_problems(_values(), []) == []
