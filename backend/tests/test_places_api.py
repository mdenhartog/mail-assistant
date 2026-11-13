# pyright: reportUnusedImport=false
"""U-web-settings-23: GET /api/places against a real session store, the real lookup and a recording limit guard."""

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import Request
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response

from app.auth.digest import username_digest
from app.auth.session import COOKIE_NAME, SessionStore, attach_sessions
from app.core.security import inventory_violations
from app.db import Database
from app.ids import SecretsIdSource
from app.main import discover_routers
from app.routers.places import Place, PlaceResults
from app.security_events import SecurityEvents
from app.startup import attach_database
from schedule_policy.places import lookup
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.fakes import FakeClock, make_app, make_settings

T0 = datetime(2026, 1, 15, 14, 0, 0, tzinfo=UTC)  # winter: Amsterdam is UTC+1, New York UTC-5
USER = username_digest(b"k" * 32, "canary-user")
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}
PATH = "/api/places"


class RecordingGuard:
    def __init__(self) -> None:
        self.buckets: list[str] = []

    async def check(self, bucket: str, request: Request) -> None:
        self.buckets.append(bucket)


class Api:
    def __init__(self, http: AsyncClient, cookie: str, guard: RecordingGuard) -> None:
        self.http = http
        self.cookie = cookie
        self.guard = guard

    async def search(self, q: str, *, signed_in: bool = True) -> Response:
        cookies = {COOKIE_NAME: self.cookie} if signed_in else {}
        return await self.http.get(PATH, params={"q": q}, cookies=cookies)


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    events = SecurityEvents(web_database, clock, b"e" * 32)
    store = SessionStore(web_database, SecretsIdSource(), events)
    app = make_app(make_settings())
    app.state.clock = clock
    guard = RecordingGuard()
    app.state.limit_guard = guard
    attach_database(app, web_database, clock)
    attach_sessions(app, store, events)
    cookie, _ = await store.create(USER, T0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, cookie, guard)


# Criterion 1
async def test_given_new_york_when_searched_then_a_hit_for_the_zone_with_label_and_offset(api: Api) -> None:
    response = await api.search("New York")

    assert response.status_code == 200
    body = response.json()
    assert body["suggestion"] is None
    assert body["places"][0] == {
        "zone": "America/New_York",
        "label": "New York, United States (UTC-5)",
        "utcOffsetMinutes": -300,
    }


# Criterion 2
async def test_given_paris_when_searched_then_at_most_five_labelled_hits(api: Api) -> None:
    response = await api.search("Paris")

    places = response.json()["places"]
    assert 1 <= len(places) <= 5
    assert places[0]["zone"] == "Europe/Paris"
    assert all(place["label"] for place in places)


async def test_given_a_one_letter_slip_when_searched_then_the_suggestion_is_new_york(api: Api) -> None:
    response = await api.search("Nwe York")

    assert response.json() == {"places": [], "suggestion": "New York"}


async def test_given_a_country_with_many_zones_when_searched_then_five_hits_at_most(api: Api) -> None:
    response = await api.search("United States")

    assert len(response.json()["places"]) == 5


# Criterion 3
@pytest.mark.parametrize("alias", ["NYC", "Wien", "Den Haag"])
async def test_given_an_alias_when_searched_then_the_result_equals_the_telegram_lookup(api: Api, alias: str) -> None:
    expected = lookup(alias, now=T0)
    assert expected.hits

    body = (await api.search(alias)).json()

    assert body["places"] == [
        {"zone": hit.zone, "label": hit.label, "utcOffsetMinutes": hit.utc_offset_minutes} for hit in expected.hits
    ]


async def test_given_accents_and_case_when_searched_then_the_result_equals_the_plain_spelling(api: Api) -> None:
    plain = (await api.search("Zurich")).json()

    accented = (await api.search("ZÜRICH")).json()

    assert plain["places"]
    assert accented == plain


# Criterion 4
async def test_given_nothing_matches_when_searched_then_an_empty_list_without_error(api: Api) -> None:
    response = await api.search("Qqqqzzzz Xxxwwvv")

    assert response.status_code == 200
    assert response.json() == {"places": [], "suggestion": None}


async def test_given_an_empty_query_when_searched_then_an_empty_list(api: Api) -> None:
    response = await api.search("")

    assert response.status_code == 200
    assert response.json()["places"] == []


# Criterion 5
async def test_given_a_65_character_query_when_searched_then_422_and_a_64_character_one_is_served(api: Api) -> None:
    too_long = await api.search("a" * 65)
    longest = await api.search("a" * 64)

    assert too_long.status_code == 422
    assert too_long.json() == {"type": "about:blank", "title": "Unprocessable content", "status": 422}
    assert longest.status_code == 200


@pytest.mark.parametrize("control", ["\x00", "\n", "\t", "\x1f", "\x7f"])
async def test_given_a_control_character_when_searched_then_422_and_nothing_is_echoed(api: Api, control: str) -> None:
    response = await api.search(f"Par{control}is")

    assert response.status_code == 422
    assert "Par" not in response.text


async def test_given_an_emoji_when_searched_then_an_empty_result_not_an_error(api: Api) -> None:
    response = await api.search("\U0001f600")

    assert response.status_code == 200
    assert response.json()["places"] == []


async def test_given_a_missing_q_when_searched_then_422(api: Api) -> None:
    response = await api.http.get(PATH, cookies={COOKIE_NAME: api.cookie})

    assert response.status_code == 422


# Criterion 6
async def test_given_a_typed_canary_when_logs_are_captured_then_no_line_holds_it(
    api: Api, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    await api.search("canary-place-xyzzy")
    await api.search("canary-place-xyzzy" + "x" * 60)
    await api.search("canary-\x00place-xyzzy")

    logged = "\n".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert "xyzzy" not in logged


# Criterion 7
async def test_given_no_session_when_searched_then_401(api: Api) -> None:
    response = await api.search("Paris", signed_in=False)

    assert response.status_code == 401
    assert response.json() == GENERIC_401


async def test_given_a_search_when_answered_then_it_counts_against_the_api_bucket(api: Api) -> None:
    await api.search("Paris")

    assert api.guard.buckets == ["api"]


# Criterion 8
def test_given_the_response_models_when_checked_then_only_the_four_names_exist() -> None:
    assert set(Place.model_json_schema()["properties"]) == {"zone", "label", "utcOffsetMinutes"}
    assert set(PlaceResults.model_json_schema()["properties"]) == {"places", "suggestion"}


def test_given_the_mounted_routes_when_read_then_places_is_one_route_and_passes_the_inventory() -> None:
    routes = [
        (mounted.prefix + route.path, route)
        for mounted in discover_routers()
        for route in mounted.router.routes
        if isinstance(route, APIRoute)
    ]
    places = [(path, route) for path, route in routes if path == PATH]

    assert len(places) == 1
    assert inventory_violations(places) == []
