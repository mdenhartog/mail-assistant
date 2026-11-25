# pyright: reportUnusedImport=false
"""U-label-prefix-removal-10: the waiting time, protection and retention on the Settings route (ADR-0060 point 6)."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.cookies import COOKIE_NAME
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
from tests.fakes import FakeClock, make_app, make_settings

T0 = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)
CSRF_KEY = b"b" * 32
ORIGIN = "https://settings.example.test"
USER = username_digest(b"k" * 32, "canary-user")
SCHEDULE = {
    "timeZone": "Europe/Amsterdam",
    "quietStart": "23:00",
    "quietEnd": "07:00",
    "overviewAt": "18:00",
    "remindAt": "09:00",
}
CLEANUP_DEFAULTS = {"waitingMinutes": 720, "protectionDays": 7, "retentionDays": 30}
RANGES = {
    "waitingMinutes": {"min": 5, "max": 720, "default": 720},
    "protectionDays": {"min": 1, "max": 30, "default": 7},
    "retentionDays": {"min": 7, "max": 90, "default": 30},
}
COUNT = "select count(*) from settings.schedule"


@dataclass
class Api:
    http: AsyncClient
    store: SessionStore
    database: Database


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    store = SessionStore(web_database, SecretsIdSource(), SecurityEvents(web_database, clock, b"e" * 32))
    app = make_app(make_settings())
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, SecurityEvents(web_database, clock, b"e" * 32))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, store, web_database)


async def _send(  # noqa: PLR0913  # the request and the two switches that leave a part out
    api: Api, method: str, path: str, body: Any = None, *, cookie: bool = True, token: bool = True
) -> Any:
    value, created = await api.store.create(USER, T0)
    headers = {"Origin": ORIGIN}
    if token:
        headers["X-CSRF-Token"] = csrf_token(CSRF_KEY, created.id_hash)
    return await api.http.request(
        method, path, json=body, headers=headers, cookies={COOKIE_NAME: value} if cookie else {}
    )


async def _put(api: Api, patch: dict[str, Any], version: int = 0, **switches: Any) -> Any:
    values = {**SCHEDULE, **CLEANUP_DEFAULTS, **patch}
    return await _send(api, "PUT", "/api/settings", {"values": values, "version": version}, **switches)


async def _get(api: Api) -> Any:
    value, _ = await api.store.create(USER, T0)
    return await api.http.get("/api/settings", cookies={COOKIE_NAME: value})


# Criterion 1 (AC 12, 33)
async def test_given_no_stored_settings_when_read_then_the_defaults_and_ranges_are_shown(api: Api) -> None:
    body = (await _get(api)).json()

    assert {k: body["values"][k] for k in CLEANUP_DEFAULTS} == CLEANUP_DEFAULTS
    assert body["ranges"] == RANGES


async def test_given_a_stored_schedule_row_from_before_this_feature_when_read_then_the_column_defaults_are_shown(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await owner.execute(
        "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, version, "
        "updated_via, updated_by) values (1, 'Europe/Amsterdam', 1380, 420, 1080, 540, 1, 'web', "
        "'web:0123456789abcdef0123456789abcdef')"
    )

    body = (await _get(api)).json()

    assert {k: body["values"][k] for k in CLEANUP_DEFAULTS} == CLEANUP_DEFAULTS
    assert body["ranges"] == RANGES


# Criterion 2 (AC 33)
@pytest.mark.parametrize(
    "patch",
    [
        {"waitingMinutes": 5},
        {"waitingMinutes": 720},
        {"waitingMinutes": 90, "protectionDays": 1, "retentionDays": 7},
        {"protectionDays": 30, "retentionDays": 90},
    ],
)
async def test_given_values_inside_their_ranges_when_saved_then_they_are_stored_and_read_back(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    patch: dict[str, int],
) -> None:
    saved = await _put(api, patch)
    read = await _get(api)

    expected = {**CLEANUP_DEFAULTS, **patch}
    assert saved.status_code == 200
    assert {k: saved.json()["values"][k] for k in expected} == expected
    assert {k: read.json()["values"][k] for k in expected} == expected
    row = await owner.fetchrow(
        "select label_wait_minutes, label_protection_days, label_retention_days from settings.schedule"
    )
    assert row is not None
    assert tuple(row.values()) == (expected["waitingMinutes"], expected["protectionDays"], expected["retentionDays"])


async def test_given_a_second_save_when_it_changes_one_value_then_the_version_rises_and_the_value_is_stored(
    api: Api,
) -> None:
    await _put(api, {})

    second = await _put(api, {"protectionDays": 14}, version=1)

    assert second.status_code == 200
    assert (second.json()["version"], second.json()["values"]["protectionDays"]) == (2, 14)


async def test_given_a_reset_when_made_then_the_cleanup_values_return_to_their_defaults(api: Api) -> None:
    await _put(api, {"waitingMinutes": 30, "protectionDays": 3, "retentionDays": 10})

    reset = await _send(api, "POST", "/api/settings/reset", {"version": 1})

    assert reset.status_code == 200
    assert {k: reset.json()["values"][k] for k in CLEANUP_DEFAULTS} == CLEANUP_DEFAULTS


# Criterion 3 (AC 33) and 7 (AC 34)
@pytest.mark.parametrize(
    ("field", "value", "rule"),
    [
        ("waitingMinutes", 4, "wait_minutes_out_of_range"),
        ("waitingMinutes", 721, "wait_minutes_out_of_range"),
        ("waitingMinutes", 0, "wait_minutes_out_of_range"),
        ("waitingMinutes", -5, "wait_minutes_out_of_range"),
        ("protectionDays", 0, "protection_days_out_of_range"),
        ("protectionDays", -1, "protection_days_out_of_range"),
        ("protectionDays", 31, "protection_days_out_of_range"),
        ("retentionDays", 6, "retention_days_out_of_range"),
        ("retentionDays", 91, "retention_days_out_of_range"),
    ],
)
async def test_given_a_value_outside_its_range_when_saved_then_422_names_the_field_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    field: str,
    value: int,
    rule: str,
) -> None:
    response = await _put(api, {field: value})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert [(p["field"], p["rule"], p["value"]) for p in response.json()["problems"]] == [(field, rule, str(value))]
    assert response.json()["problems"][0]["example"] == str(RANGES[field]["default"])
    assert await owner.fetchval(COUNT) == 0


async def test_given_several_broken_values_when_saved_then_every_field_is_named(api: Api) -> None:
    response = await _put(api, {"waitingMinutes": 1, "protectionDays": 0, "timeZone": "Mars/Olympus"})

    assert {p["field"] for p in response.json()["problems"]} == {"waitingMinutes", "protectionDays", "timeZone"}


@pytest.mark.parametrize("value", ["12", 7.5, True, None, [7]])
async def test_given_a_value_that_is_not_a_whole_number_when_saved_then_422_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    value: Any,
) -> None:
    response = await _put(api, {"protectionDays": value})

    assert response.status_code == 422
    assert await owner.fetchval(COUNT) == 0


async def test_given_a_value_missing_when_saved_then_422(api: Api) -> None:
    values = {**SCHEDULE, "waitingMinutes": 60, "protectionDays": 7}

    response = await _send(api, "PUT", "/api/settings", {"values": values, "version": 0})

    assert response.status_code == 422


# Criterion 5
@pytest.mark.parametrize(("cookie", "token", "status"), [(False, True, 401), (True, False, 403)])
async def test_given_no_session_or_no_csrf_token_when_saved_then_refused_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    cookie: bool,
    token: bool,
    status: int,
) -> None:
    response = await _put(api, {"waitingMinutes": 30}, cookie=cookie, token=token)

    assert response.status_code == status
    assert await owner.fetchval(COUNT) == 0


# Criterion 6
@pytest.mark.parametrize("extra", [{"waitingHours": 3}, {"otherLabel": "Rest"}, {"archiveLabel": "Kept"}])
async def test_given_an_unknown_field_among_the_values_when_saved_then_422_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    extra: dict[str, Any],
) -> None:
    response = await _put(api, extra)

    assert response.status_code == 422
    assert await owner.fetchval(COUNT) == 0


async def test_given_the_ranges_sent_back_when_saved_then_422_because_they_are_read_only(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    body = {"values": {**SCHEDULE, **CLEANUP_DEFAULTS}, "version": 0, "ranges": RANGES}

    response = await _send(api, "PUT", "/api/settings", body)

    assert response.status_code == 422
    assert await owner.fetchval(COUNT) == 0


# Criterion 8
async def test_given_a_change_of_the_waiting_time_when_saved_then_the_audit_row_shows_it_without_label_names(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await _put(api, {})
    await _put(api, {"waitingMinutes": 45}, version=1)

    rows = await owner.fetch("select via, by, old, new from settings.settings_change order by (new->>'version')::int")

    assert [(r["via"], r["by"]) for r in rows] == [("web", f"web:{USER}")] * 2
    old, new = json.loads(rows[1]["old"]), json.loads(rows[1]["new"])
    assert (old["label_wait_minutes"], new["label_wait_minutes"]) == (720, 45)
    assert not [key for key in new if "name" in key or key.endswith("_label")]
