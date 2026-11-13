# pyright: reportUnusedImport=false
"""U-web-settings-20: GET /api/settings, the rule-to-field map and the checked-in OpenAPI document."""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.auth.digest import username_digest
from app.auth.session import COOKIE_NAME, SessionStore, attach_sessions
from app.db import Database
from app.errors import RateLimited
from app.export_openapi import DEFAULT_TARGET, build_document
from app.ids import SecretsIdSource
from app.security_events import SecurityEvents
from app.settings_fields import FIELD_OF_RULE
from app.settings_repo import SettingsRepository
from app.startup import attach_database
from schedule_policy import RULES
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
USER = username_digest(b"k" * 32, "canary-user")
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}
GENERIC_429 = {"type": "about:blank", "title": "Too many requests", "status": 429}
DEFAULTS = {
    "timeZone": "Europe/Amsterdam",
    "quietStart": "23:00",
    "quietEnd": "07:00",
    "overviewAt": "18:00",
    "remindAt": "09:00",
}
STORED = {
    "timeZone": "America/New_York",
    "quietStart": "22:30",
    "quietEnd": "06:45",
    "overviewAt": "18:05",
    "remindAt": "09:15",
}
TIME_FIELDS = ("quietStart", "quietEnd", "overviewAt", "remindAt")
INSERT_ROW = (
    "insert into settings.schedule "
    "(id, zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_at, updated_via, updated_by) "
    "values (1, 'America/New_York', 1350, 405, 1085, 555, 1, now(), 'web', 'web:0123456789abcdef0123456789abcdef')"
)


class CountingGuard:
    """A limit guard that lets ``allowed`` requests through and refuses the rest."""

    def __init__(self, allowed: int) -> None:
        self.allowed = allowed
        self.buckets: list[str] = []

    async def check(self, bucket: str, request: Request) -> None:
        self.buckets.append(bucket)
        if len(self.buckets) > self.allowed:
            raise RateLimited(30)


@dataclass
class Api:
    http: AsyncClient
    app: FastAPI


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def store(web_database: Database, clock: FakeClock) -> SessionStore:  # noqa: F811
    return SessionStore(web_database, SecretsIdSource(), SecurityEvents(web_database, clock, b"e" * 32))


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count the reads that reach the repository."""
    calls: list[int] = []
    original = SettingsRepository.read

    async def spy(self: SettingsRepository) -> Any:
        calls.append(1)
        return await original(self)

    monkeypatch.setattr(SettingsRepository, "read", spy)
    return calls


@pytest.fixture
async def api(web_database: Database, clock: FakeClock, store: SessionStore) -> AsyncIterator[Api]:  # noqa: F811
    app = make_app(make_settings())
    app.state.clock = clock
    app.state.limit_guard = CountingGuard(allowed=30)
    attach_database(app, web_database, clock)
    attach_sessions(app, store, SecurityEvents(web_database, clock, b"e" * 32))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, app)


async def _cookie(store: SessionStore) -> dict[str, str]:
    value, _ = await store.create(USER, T0)
    return {COOKIE_NAME: value}


async def _seed(owner: asyncpg.Connection) -> datetime:  # noqa: F811
    """Insert the stored row as the owner; the server stamps ``updated_at``, which is returned."""
    await owner.execute(INSERT_ROW)
    return await owner.fetchval("select updated_at from settings.schedule where id = 1")


# Criterion 1
async def test_given_a_stored_row_when_settings_are_read_then_values_version_time_and_channel(
    api: Api,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    changed_at = await _seed(owner)

    response = await api.http.get("/api/settings", cookies=await _cookie(store))

    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body.pop("updatedAt")) == changed_at
    assert body == {"values": STORED, "version": 1, "updatedVia": "web"}


async def test_given_a_stored_row_when_settings_are_read_then_no_actor_is_in_the_answer(
    api: Api,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _seed(owner)

    response = await api.http.get("/api/settings", cookies=await _cookie(store))

    assert set(response.json()) == {"values", "version", "updatedAt", "updatedVia"}
    assert "web:0123" not in response.text
    assert "updatedBy" not in response.text


# Criterion 2
async def test_given_no_row_when_settings_are_read_then_the_defaults_at_version_zero(
    api: Api, store: SessionStore
) -> None:
    response = await api.http.get("/api/settings", cookies=await _cookie(store))

    assert response.status_code == 200
    assert response.json() == {"values": DEFAULTS, "version": 0, "updatedAt": None, "updatedVia": None}


async def test_given_no_row_when_the_repository_reads_then_it_returns_the_defaults_at_version_zero(
    web_database: Database,  # noqa: F811
) -> None:
    stored = await SettingsRepository(web_database).read()

    assert (stored.version, stored.updated_at, stored.updated_via) == (0, None, None)
    assert stored.policy.zone == "Europe/Amsterdam"


async def test_given_a_stored_row_when_the_repository_reads_then_minutes_become_wall_clock_times(
    web_database: Database,  # noqa: F811
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    changed_at = await _seed(owner)

    stored = await SettingsRepository(web_database).read()

    assert stored.policy.zone == "America/New_York"
    assert [t.isoformat() for t in (stored.policy.quiet_start, stored.policy.quiet_end)] == ["22:30:00", "06:45:00"]
    assert [t.isoformat() for t in (stored.policy.overview_at, stored.policy.remind_at)] == ["18:05:00", "09:15:00"]
    assert (stored.version, stored.updated_at, stored.updated_via) == (1, changed_at, "web")


# Criterion 3
def test_given_the_package_rules_and_the_field_map_when_compared_then_every_rule_has_a_field_and_nothing_extra() -> (
    None
):
    assert RULES
    assert set(FIELD_OF_RULE) == set(RULES)


def test_given_a_new_rule_in_the_package_when_the_map_is_compared_then_the_comparison_fails() -> None:
    assert set(FIELD_OF_RULE) != {*RULES, "a_new_rule"}


# Criterion 4
def test_given_the_window_rules_when_mapped_then_start_and_end() -> None:
    assert FIELD_OF_RULE["quiet_window_empty"] == ("quietStart", "quietEnd")
    assert FIELD_OF_RULE["quiet_window_length"] == ("quietStart", "quietEnd")


def test_given_the_quiet_hours_and_zone_rules_when_mapped_then_overview_remind_and_zone() -> None:
    assert FIELD_OF_RULE["overview_in_quiet_hours"] == ("overviewAt",)
    assert FIELD_OF_RULE["remind_in_quiet_hours"] == ("remindAt",)
    assert FIELD_OF_RULE["zone_unknown"] == ("timeZone",)


def test_given_the_malformed_time_rules_when_mapped_then_they_name_the_four_time_fields() -> None:
    assert FIELD_OF_RULE["time_not_whole_minute"] == TIME_FIELDS
    assert FIELD_OF_RULE["time_has_zone"] == TIME_FIELDS


# Criterion 5
async def test_given_no_session_when_settings_are_read_then_401_and_nothing_is_read(api: Api, reads: list[int]) -> None:
    response = await api.http.get("/api/settings")

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert reads == []


async def test_given_an_expired_session_when_settings_are_read_then_401_and_nothing_is_read(
    api: Api, store: SessionStore, clock: FakeClock, reads: list[int]
) -> None:
    cookies = await _cookie(store)
    clock.set(datetime(2026, 3, 2, 14, 0, 0, tzinfo=UTC))

    response = await api.http.get("/api/settings", cookies=cookies)

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert reads == []


async def test_given_a_locked_web_when_settings_are_read_then_401_and_nothing_is_read(
    api: Api,
    store: SessionStore,
    owner: asyncpg.Connection,  # noqa: F811
    reads: list[int],
) -> None:
    cookies = await _cookie(store)
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", T0)

    response = await api.http.get("/api/settings", cookies=cookies)

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert reads == []


# Criterion 7
async def test_given_a_guard_that_refuses_the_31st_request_when_settings_are_read_then_429_on_the_31st(
    api: Api, store: SessionStore
) -> None:
    cookies = await _cookie(store)
    guard: CountingGuard = api.app.state.limit_guard

    statuses = [(await api.http.get("/api/settings", cookies=cookies)).status_code for _ in range(31)]

    assert statuses == [200] * 30 + [429]
    assert set(guard.buckets) == {"api"}


async def test_given_a_refusing_guard_when_settings_are_read_then_429_with_retry_after_and_nothing_is_read(
    api: Api, store: SessionStore, reads: list[int]
) -> None:
    cookies = await _cookie(store)
    api.app.state.limit_guard = CountingGuard(allowed=0)

    response = await api.http.get("/api/settings", cookies=cookies)

    assert response.status_code == 429
    assert response.json() == GENERIC_429
    assert response.headers["retry-after"] == "30"
    assert reads == []


# Criterion 6
def _document() -> dict[str, Any]:
    return json.loads(DEFAULT_TARGET.read_text(encoding="utf-8"))


def _schemas() -> dict[str, Any]:
    return _document()["components"]["schemas"]


def _refs(document: dict[str, Any]) -> list[str]:
    return re.findall(r'"\$ref": "([^"]+)"', json.dumps(document))


def test_given_the_exported_document_when_read_then_it_is_the_one_the_code_generates() -> None:
    assert DEFAULT_TARGET.read_text(encoding="utf-8") == build_document()


@pytest.mark.parametrize("name", ["Settings", "SettingsValues", "SettingsUpdate", "Problem422", "Conflict409"])
def test_given_the_exported_document_when_read_then_each_settings_schema_forbids_extra_properties(name: str) -> None:
    assert _schemas()[name]["additionalProperties"] is False


def test_given_the_exported_document_when_read_then_settings_has_get_and_put_and_no_reset() -> None:
    assert list(_document()["paths"]["/api/settings"]) == ["get", "put"]
    assert "/api/settings/reset" not in _document()["paths"]


def test_given_the_exported_document_when_read_then_times_are_hhmm_and_no_actor_is_exposed() -> None:
    values = _schemas()["SettingsValues"]["properties"]
    settings = _schemas()["Settings"]["properties"]

    assert {name: values[name]["pattern"] for name in TIME_FIELDS} == dict.fromkeys(
        TIME_FIELDS, r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )
    assert set(settings) == {"values", "version", "updatedAt", "updatedVia"}


def test_given_the_exported_document_when_read_then_every_reference_resolves() -> None:
    names = {f"#/components/schemas/{name}" for name in _schemas()}

    assert set(_refs(_document())) <= names


def test_given_the_exported_document_when_read_then_get_settings_declares_401_and_429() -> None:
    responses = _document()["paths"]["/api/settings"]["get"]["responses"]

    assert {"200", "401", "429"} <= set(responses)
