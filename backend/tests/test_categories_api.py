# pyright: reportUnusedImport=false
"""U-mail-categories-04: GET and PUT /api/categories against a real PostgreSQL, written as the web role.

The list is seeded as the owner of the schema; the audit and the counts are read as the owner too (the web role has no
privilege on the audit).
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI
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
MAILBOX = "primary"
OTHER_MAILBOX = "second"
NIL = "00000000-0000-0000-0000-000000000000"
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}
GENERIC_403 = {"type": "about:blank", "title": "Forbidden", "status": 403}
VERSIONS = "select count(*) from categories.list_version where mailbox_id = $1"


@dataclass
class Api:
    http: AsyncClient
    app: FastAPI
    store: SessionStore


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    store = SessionStore(web_database, SecretsIdSource(), SecurityEvents(web_database, clock, b"e" * 32))
    app = make_app(make_settings(categories_mailbox_id=MAILBOX))
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, SecurityEvents(web_database, clock, b"e" * 32))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, app, store)


async def seed(
    owner: asyncpg.Connection,  # noqa: F811
    categories: list[tuple[str, str]],
    *,
    version: int = 1,
    mailbox: str = MAILBOX,
) -> list[str]:
    """Write one list version as the owner and return the ids in order."""
    ids = [str(uuid.uuid4()) for _ in categories]
    async with owner.transaction():
        await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", mailbox)
        await owner.execute(
            "insert into categories.list_version (mailbox_id, version) values ($1, $2)", mailbox, version
        )
        for position, (cid, (name, description)) in enumerate(zip(ids, categories, strict=True)):
            await owner.execute(
                "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", mailbox, uuid.UUID(cid)
            )
            await owner.execute(
                "insert into categories.category (mailbox_id, version, id, name, description, position) "
                "values ($1, $2, $3, $4, $5, $6)",
                mailbox,
                version,
                uuid.UUID(cid),
                name,
                description,
                position,
            )
    return ids


async def count(owner: asyncpg.Connection, category_id: str, mails: int, mailbox: str = MAILBOX) -> None:  # noqa: F811
    await owner.execute(
        "insert into categories.category_count (mailbox_id, category_id, mail_count) values ($1, $2, $3)",
        mailbox,
        uuid.UUID(category_id),
        mails,
    )


async def label(owner: asyncpg.Connection, name: str, mailbox: str = MAILBOX) -> None:  # noqa: F811
    await owner.execute("insert into categories.gmail_label (mailbox_id, name) values ($1, $2)", mailbox, name)


async def request(  # noqa: PLR0913  # one switch per part of the request that a test may leave out
    api: Api,
    method: str,
    body: Any = None,
    *,
    cookie: bool = True,
    token: bool = True,
    origin: str | None = ORIGIN,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    """Send a request as a new signed-in session; the switches leave out one part of it."""
    value, created = await api.store.create(USER, T0)
    headers: dict[str, str] = dict(extra_headers or {})
    if token:
        headers["X-CSRF-Token"] = csrf_token(CSRF_KEY, created.id_hash)
    if origin is not None:
        headers["Origin"] = origin
    return await api.http.request(
        method, "/api/categories", json=body, headers=headers, cookies={COOKIE_NAME: value} if cookie else {}
    )


async def get(api: Api, **switches: Any) -> Any:
    return await request(api, "GET", **switches)


async def put(api: Api, version: int, categories: list[dict[str, Any]], **switches: Any) -> Any:
    return await request(api, "PUT", {"version": version, "categories": categories}, **switches)


def entry(name: str, description: str = "Things that belong here", id_: str | None = None) -> dict[str, Any]:
    return {"name": name, "description": description, **({"id": id_} if id_ else {})}


# Criterion 1
async def test_given_a_list_with_counts_and_labels_when_get_then_the_list_other_and_older_categories_are_returned(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    invoices, travel = await seed(owner, [("Invoices", "Bills and receipts"), ("Travel", "Tickets and bookings")])
    await count(owner, invoices, 5)
    await count(owner, NIL, 3)
    for name in ("Assistant/Invoices", "Assistant/Travel", "Assistant/Old stuff", "Assistant/Archive", "Work"):
        await label(owner, name)
    await seed(owner, [("Elsewhere", "Not mine")], mailbox=OTHER_MAILBOX)

    response = await get(api)

    assert response.status_code == 200
    assert response.json() == {
        "version": 1,
        "ready": True,
        "categories": [
            {"id": invoices, "name": "Invoices", "description": "Bills and receipts", "mailCount": 5},
            {"id": travel, "name": "Travel", "description": "Tickets and bookings", "mailCount": 0},
        ],
        "other": {"mailCount": 3},
        "olderCategories": [{"labelName": "Assistant/Old stuff", "mailCount": None}],
    }


async def test_given_no_seed_yet_when_get_then_version_0_and_not_ready(api: Api) -> None:
    response = await get(api)

    assert response.status_code == 200
    assert response.json() == {
        "version": 0,
        "ready": False,
        "categories": [],
        "other": {"mailCount": 0},
        "olderCategories": [],
    }


# Criterion 2
async def test_given_a_valid_list_at_the_current_version_when_put_then_200_a_new_version_and_one_audit_record(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    invoices, travel = await seed(owner, [("Invoices", "Bills"), ("Travel", "Trips")])

    response = await put(
        api,
        1,
        [entry("Receipts", "Bills and receipts", invoices), entry("Newsletters"), entry("Travel", "Trips", travel)],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert [(c["name"], c["description"]) for c in body["categories"]] == [
        ("Receipts", "Bills and receipts"),
        ("Newsletters", "Things that belong here"),
        ("Travel", "Trips"),
    ]
    assert body["categories"][0]["id"] == invoices
    assert body["categories"][2]["id"] == travel
    assert body["categories"][1]["id"] not in {invoices, travel}
    assert (await get(api)).json() == body
    audit = await owner.fetch("select version, channel, actor_digest, new_list from categories.list_audit order by 1")
    assert [(row["version"], row["channel"]) for row in audit] == [(1, "operator"), (2, "web")]
    assert len(audit[1]["actor_digest"]) == 64


async def test_given_an_unchanged_list_when_put_then_200_at_the_same_version_and_no_new_version(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    invoices, travel = await seed(owner, [("Invoices", "Bills"), ("Travel", "Trips")])

    response = await put(api, 1, [entry(" Invoices ", " Bills ", invoices), entry("Travel", "Trips", travel)])

    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_the_same_names_in_another_order_when_put_then_it_is_a_new_version(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    invoices, travel = await seed(owner, [("Invoices", "Bills"), ("Travel", "Trips")])

    response = await put(api, 1, [entry("Travel", "Trips", travel), entry("Invoices", "Bills", invoices)])

    assert response.status_code == 200
    assert [c["name"] for c in response.json()["categories"]] == ["Travel", "Invoices"]
    assert response.json()["version"] == 2


# Criterion 3
@pytest.mark.parametrize(
    ("categories", "rule", "field", "index"),
    [
        ([entry("")], "name_empty", "name", 0),
        ([entry("   ")], "name_empty", "name", 0),
        ([entry("x" * 41)], "name_too_long", "name", 0),
        ([entry("a/b")], "name_slash", "name", 0),
        ([entry("a" + chr(0x202E) + "b")], "name_forbidden_char", "name", 0),
        ([entry("Other")], "name_reserved", "name", 0),
        ([entry(" OTHER ")], "name_reserved", "name", 0),
        ([entry("Archive")], "name_reserved", "name", 0),
        ([entry("Bills"), entry("bills")], "name_duplicate", "name", 1),
        ([entry("Bills", "")], "description_empty", "description", 0),
        ([entry("Bills", "d" * 501)], "description_too_long", "description", 0),
        ([entry(f"C{n}") for n in range(51)], "list_too_many", "list", None),
        ([entry("Old stuff")], "name_label_exists", "name", 0),
        ([entry("Bills", id_=str(uuid.uuid4()))], "id_unknown", "id", 0),
    ],
)
async def test_given_an_invalid_rule_when_put_then_422_with_problems_and_nothing_is_stored(  # noqa: PLR0913, PLR0917
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    categories: list[dict[str, Any]],
    rule: str,
    field: str,
    index: int | None,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    await label(owner, "Assistant/Old stuff")

    response = await put(api, 1, categories)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert (body["type"], body["title"], body["status"]) == ("about:blank", "Unprocessable content", 422)
    assert {"rule": rule, "field": field, "index": index} in body["problems"]
    assert all(set(problem) == {"rule", "field", "index"} for problem in body["problems"])
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_a_duplicate_id_when_put_then_422_id_duplicate(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    (invoices,) = await seed(owner, [("Invoices", "Bills")])

    response = await put(api, 1, [entry("A", id_=invoices), entry("B", id_=invoices)])

    assert response.status_code == 422
    assert {"rule": "id_duplicate", "field": "id", "index": 1} in response.json()["problems"]


async def test_given_the_empty_list_when_put_then_other_stays_and_cannot_be_deleted_or_renamed(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    await count(owner, NIL, 4)

    emptied = await put(api, 1, [])
    renamed = await request(api, "PUT", {"version": 2, "categories": [], "other": {"name": "Rest"}})

    assert emptied.status_code == 200
    assert emptied.json()["categories"] == []
    assert emptied.json()["other"] == {"mailCount": 4}
    assert renamed.status_code == 422
    assert await owner.fetchval(VERSIONS, MAILBOX) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"version": 1, "categories": [entry("A")], "extra": 1},
        {"version": 1, "categories": [{"name": "A", "description": "d", "position": 3}]},
        {"version": -1, "categories": []},
        {"categories": []},
        {"version": 1},
        {"version": 1, "categories": [{"name": 5, "description": "d"}]},
        {"version": 1, "categories": [{"name": "A", "description": "d", "id": "not-a-uuid"}]},
    ],
)
async def test_given_a_malformed_body_when_put_then_422_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    body: Any,
) -> None:
    await seed(owner, [("Invoices", "Bills")])

    response = await request(api, "PUT", body)

    assert response.status_code == 422
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_a_non_json_body_when_put_then_415(api: Api) -> None:
    value, created = await api.store.create(USER, T0)

    response = await api.http.put(
        "/api/categories",
        content='{"version": 0, "categories": []}',
        headers={"Content-Type": "text/plain", "Origin": ORIGIN, "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash)},
        cookies={COOKIE_NAME: value},
    )

    assert response.status_code == 415


# Criterion 4
async def test_given_a_stale_version_when_put_then_409_with_the_current_list_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    (invoices,) = await seed(owner, [("Invoices", "Bills")])

    response = await put(api, 0, [entry("Mine")])

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert (body["type"], body["title"], body["status"], body["reason"]) == ("about:blank", "Conflict", 409, "version")
    assert body["current"]["version"] == 1
    assert body["current"]["categories"][0]["id"] == invoices
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_the_seed_not_yet_written_when_put_then_409_not_ready_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    response = await put(api, 0, [entry("Mine")])

    assert response.status_code == 409
    body = response.json()
    assert body["reason"] == "not-ready"
    assert body["current"]["ready"] is False
    assert await owner.fetchval("select count(*) from categories.list_version") == 0


async def test_given_two_saves_at_the_same_version_when_sent_together_then_one_wins_and_the_other_gets_409(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])

    first, second = await asyncio.gather(put(api, 1, [entry("One")]), put(api, 1, [entry("Two")]))

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert await owner.fetchval(VERSIONS, MAILBOX) == 2


# Criterion 5
async def test_given_ten_saves_in_an_hour_when_the_eleventh_comes_from_a_new_session_then_429_with_retry_after(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    for number in range(10):
        saved = await put(api, number + 1, [entry(f"Name {number}")])
        assert saved.status_code == 200

    refused = await put(api, 11, [entry("Name 10")])
    unchanged = await put(api, 11, [entry("Name 9")])

    assert refused.status_code == 429
    assert 1 <= int(refused.headers["retry-after"]) <= 3600
    assert refused.json() == {"type": "about:blank", "title": "Too many requests", "status": 429}
    assert refused.headers["cache-control"] == "no-store"
    assert unchanged.status_code == 429
    assert await owner.fetchval(VERSIONS, MAILBOX) == 11


async def test_given_saves_older_than_an_hour_when_put_then_they_do_not_count(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    for number in range(10):
        assert (await put(api, number + 1, [entry(f"Name {number}")])).status_code == 200
    await owner.execute("update categories.list_version set created_at = now() - interval '61 minutes'")

    response = await put(api, 11, [entry("Fresh")])

    assert response.status_code == 200


async def test_given_the_limit_when_another_mailbox_saves_then_it_counts_separately(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    for number in range(10):
        assert (await put(api, number + 1, [entry(f"Name {number}")])).status_code == 200
    await seed(owner, [("Elsewhere", "Not mine")], mailbox=OTHER_MAILBOX)

    assert (await put(api, 11, [entry("Name 10")])).status_code == 429
    assert (await get(api)).json()["version"] == 11


# Criterion 6
@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_given_no_session_when_called_then_401_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    method: str,
) -> None:
    await seed(owner, [("Invoices", "Bills")])

    response = await request(api, method, {"version": 1, "categories": []} if method == "PUT" else None, cookie=False)

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


@pytest.mark.parametrize(
    ("token", "origin"),
    [(False, ORIGIN), (True, None), (True, "https://evil.example.test"), (False, None)],
)
async def test_given_no_token_or_a_wrong_origin_when_put_then_403_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    token: bool,
    origin: str | None,
) -> None:
    await seed(owner, [("Invoices", "Bills")])

    response = await put(api, 1, [entry("Mine")], token=token, origin=origin)

    assert response.status_code == 403
    assert response.json() == GENERIC_403
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_a_cross_site_request_when_put_then_403(api: Api) -> None:
    response = await put(api, 1, [], extra_headers={"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == 403
    assert response.json() == GENERIC_403


@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_given_the_web_lock_when_called_then_401_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    method: str,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    value, created = await api.store.create(USER, T0)
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", T0)

    response = await api.http.request(
        method,
        "/api/categories",
        json={"version": 1, "categories": []} if method == "PUT" else None,
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash)},
        cookies={COOKIE_NAME: value},
    )

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


# Criterion 7
async def test_given_markup_in_a_name_and_description_when_saved_then_it_is_stored_and_returned_as_text(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    # A name may not hold a slash (it is a label name), so the markup of the name has none; the description may.
    name, description = "<img src=x onerror=alert(1)>", "<script>alert(1)</script>"

    saved = await put(api, 1, [entry(name, description)])
    read = await get(api)

    for response in (saved, read):
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["categories"][0]["name"] == name
        assert response.json()["categories"][0]["description"] == description
    assert await owner.fetchval("select name from categories.category where version = 2") == name


async def test_given_any_outcome_when_called_then_the_response_carries_no_store(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])

    responses = [await put(api, 0, []), await put(api, 1, [entry("")]), await get(api, cookie=False)]

    assert [r.status_code for r in responses] == [409, 422, 401]
    assert {r.headers["cache-control"] for r in responses} == {"no-store"}


# Criterion 8 (contract): the schema names of the settings API stay as they were; the list API has its own.
async def test_given_the_openapi_document_when_read_then_the_settings_schemas_keep_their_names(api: Api) -> None:
    schemas = api.app.openapi()["components"]["schemas"]

    assert schemas["Conflict409"]["properties"]["current"] == {"$ref": "#/components/schemas/Settings"}
    assert schemas["Problem422"]["properties"]["problems"]["items"] == {"$ref": "#/components/schemas/ProblemItem"}
    assert schemas["CategoryConflict409"]["properties"]["current"] == {"$ref": "#/components/schemas/CategoryList"}
    assert schemas["CategoryProblem422"]["properties"]["problems"]["items"] == {
        "$ref": "#/components/schemas/CategoryProblem"
    }
    assert not [name for name in schemas if "__" in name]


# Guardrail-fastapi: both routes count against the api bucket before anything else.
async def test_given_a_call_when_sent_then_it_counts_against_the_api_bucket(api: Api) -> None:
    buckets: list[str] = []

    class Guard:
        async def check(self, bucket: str, _request: Any) -> None:
            buckets.append(bucket)

    api.app.state.limit_guard = Guard()

    await get(api)
    await put(api, 0, [])

    assert buckets == ["api", "api"]
