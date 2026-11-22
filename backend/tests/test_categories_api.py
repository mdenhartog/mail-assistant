# pyright: reportUnusedImport=false
"""U-mail-categories-04: GET and PUT /api/categories against a real PostgreSQL, written as the web role.

The list is seeded as the owner of the schema; the audit and the counts are read as the owner too (the web role has no
privilege on the audit).
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.auth.cookies import COOKIE_NAME
from app.auth.csrf import csrf_token
from app.auth.digest import username_digest
from app.auth.session import SessionStore, attach_sessions
from app.categories_models import CategoryInput, SenderItem
from app.categories_repo import StoredCategory, StoredList
from app.categories_write import problems_of
from app.db import Database
from app.ids import SecretsIdSource
from app.security_events import SecurityEvents
from app.startup import attach_database
from category_policy import Kind
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.fakes import FakeClock, make_app, make_settings, real_minute

T0 = real_minute()  # the list versions carry the database's clock, so the app's fake clock starts at the real time
CSRF_KEY = b"b" * 32
ORIGIN = "https://settings.example.test"
USER = username_digest(b"k" * 32, "canary-user")
MAILBOX = "primary"
OTHER_MAILBOX = "second"
NIL = "00000000-0000-0000-0000-000000000000"
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}
GENERIC_403 = {"type": "about:blank", "title": "Forbidden", "status": 403}
CASES: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[2] / "packages/category-policy/contract/category_cases.json").read_text("utf-8")
)
ARCHIVE = "Assistant/Archive"
SENDER_CASES: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[2] / "packages/category-policy/contract/sender_cases.json").read_text("utf-8")
)
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


async def seed(  # noqa: PLR0913  # the switches say which parts of the v2 list the test needs
    owner: asyncpg.Connection,  # noqa: F811
    categories: list[tuple[str, str]],
    *,
    version: int = 1,
    mailbox: str = MAILBOX,
    details: dict[int, dict[str, Any]] | None = None,
    instructions: str = "",
    archive_label: str = ARCHIVE,
    settings: bool = True,
) -> list[str]:
    """Write one list version as the owner and return the ids in order.

    ``details`` maps a position to ``kind``, ``notify`` and ``senders`` (a list of ``(entry, is_domain, subdomains)``).
    """
    ids = [str(uuid.uuid4()) for _ in categories]
    async with owner.transaction():
        await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", mailbox)
        await owner.execute(
            "insert into categories.list_version (mailbox_id, version) values ($1, $2)", mailbox, version
        )
        for position, (cid, (name, description)) in enumerate(zip(ids, categories, strict=True)):
            extra = (details or {}).get(position, {})
            await owner.execute(
                "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", mailbox, uuid.UUID(cid)
            )
            await owner.execute(
                "insert into categories.category (mailbox_id, version, id, name, description, position, kind, notify) "
                "values ($1, $2, $3, $4, $5, $6, $7, $8)",
                mailbox,
                version,
                uuid.UUID(cid),
                name,
                description,
                position,
                extra.get("kind", "topic"),
                extra.get("notify", False),
            )
            for text, is_domain, subdomains in extra.get("senders", []):
                await owner.execute(
                    "insert into categories.category_sender "
                    "(mailbox_id, version, category_id, entry, is_domain, subdomains) values ($1, $2, $3, $4, $5, $6)",
                    mailbox,
                    version,
                    uuid.UUID(cid),
                    text,
                    is_domain,
                    subdomains,
                )
        if settings:
            await owner.execute(
                "insert into categories.list_settings (mailbox_id, version, general_instructions, archive_label) "
                "values ($1, $2, $3, $4)",
                mailbox,
                version,
                instructions,
                archive_label,
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
    value, created = await api.store.create(USER, api.app.state.clock.now())
    headers: dict[str, str] = dict(extra_headers or {})
    if token:
        headers["X-CSRF-Token"] = csrf_token(CSRF_KEY, created.id_hash)
    if origin is not None:
        headers["Origin"] = origin
    if cookie:  # a header, not the per-request cookies argument that httpx deprecates
        headers["Cookie"] = f"{COOKIE_NAME}={value}"
    return await api.http.request(method, "/api/categories", json=body, headers=headers)


async def get(api: Api, **switches: Any) -> Any:
    return await request(api, "GET", **switches)


async def put(
    api: Api, version: int, categories: list[dict[str, Any]], *, instructions: str = "", **switches: Any
) -> Any:
    return await request(api, "PUT", body_of(version, categories, instructions), **switches)


def body_of(version: int, categories: list[dict[str, Any]], instructions: str = "") -> dict[str, Any]:
    return {"version": version, "categories": categories, "generalInstructions": instructions}


def entry(  # noqa: PLR0913  # the fields of one category of the v2 list
    name: str,
    description: str = "Things that belong here",
    id_: str | None = None,
    *,
    kind: str = "topic",
    notify: bool = False,
    senders: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "kind": kind,
        "notify": notify,
        "senders": senders or [],
        **({"id": id_} if id_ else {}),
    }


def sender(text: str, *, subdomains: bool = False) -> dict[str, Any]:
    return {"entry": text, "subdomains": subdomains}


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
            {
                "id": invoices,
                "name": "Invoices",
                "description": "Bills and receipts",
                "kind": "topic",
                "notify": False,
                "senders": [],
                "mailCount": 5,
            },
            {
                "id": travel,
                "name": "Travel",
                "description": "Tickets and bookings",
                "kind": "topic",
                "notify": False,
                "senders": [],
                "mailCount": 0,
            },
        ],
        "generalInstructions": "",
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
        "generalInstructions": "",
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
        ([entry("x" * 41)], "name_segment_too_long", "name", 0),
        ([entry("a//b")], "name_segment_empty", "name", 0),
        ([entry("a/")], "name_segment_empty", "name", 0),
        ([entry("/".join(["x" * 40] * 6))], "name_label_too_long", "name", 0),
        ([entry("a" + chr(0x202E) + "b")], "name_forbidden_char", "name", 0),
        ([entry("Other")], "name_reserved", "name", 0),
        ([entry(" OTHER ")], "name_reserved", "name", 0),
        ([entry("Archive")], "name_reserved", "name", 0),
        ([entry("Bills"), entry("bills")], "name_duplicate", "name", 1),
        ([entry("Bills", "")], "description_empty", "description", 0),
        ([entry("Bills", "d" * 1501)], "description_too_long", "description", 0),
        ([entry(f"C{n}") for n in range(101)], "list_too_many", "list", None),
        ([entry("Invoices")], "name_label_exists", "name", 0),
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
    await label(owner, "Assistant/Invoices")
    await label(owner, "Assistant/Travel")

    response = await put(api, 1, categories)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert (body["type"], body["title"], body["status"]) == ("about:blank", "Unprocessable content", 422)
    assert {"rule": rule, "field": field, "index": index, "position": None, "otherIndex": None} in body["problems"]
    assert all(set(problem) == {"rule", "field", "index", "position", "otherIndex"} for problem in body["problems"])
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


# Criteria 1 and 3 (U-label-structure-11): the v2 list
async def test_given_a_v2_list_with_nested_names_kinds_senders_ticks_and_instructions_when_put_then_one_new_version(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    (invoices,) = await seed(owner, [("Invoices", "Bills")], archive_label="Mail/Old archive")
    categories = [
        entry("Huis / Energie", "Energy bills", notify=True, senders=[sender("Example.NL", subdomains=True)]),
        entry("Urgent", "Needs a look", kind="extra", senders=[sender("Boss@Example.com"), sender("example.nl")]),
        entry("Invoices", "Bills", invoices),
    ]

    response = await put(api, 1, categories, instructions="  I live in Utrecht.  ")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert body["generalInstructions"] == "I live in Utrecht."
    assert [(c["name"], c["kind"], c["notify"]) for c in body["categories"]] == [
        ("Huis/Energie", "topic", True),
        ("Urgent", "extra", False),
        ("Invoices", "topic", False),
    ]
    assert body["categories"][0]["senders"] == [{"entry": "example.nl", "subdomains": True, "skippedCount": 0}]
    assert body["categories"][1]["senders"] == [
        {"entry": "boss@example.com", "subdomains": False, "skippedCount": 0},
        {"entry": "example.nl", "subdomains": False, "skippedCount": 0},
    ]
    assert (await get(api)).json() == body
    rows = await owner.fetch(
        "select c.name, s.entry, s.is_domain, s.subdomains from categories.category_sender s "
        "join categories.category c on c.mailbox_id = s.mailbox_id and c.version = s.version and c.id = s.category_id "
        "where s.version = 2 order by 1, 2"
    )
    assert [tuple(row) for row in rows] == [
        ("Huis/Energie", "example.nl", True, True),
        ("Urgent", "boss@example.com", False, False),
        ("Urgent", "example.nl", True, False),
    ]
    settings = await owner.fetchrow("select * from categories.list_settings where version = 2")
    assert settings is not None
    assert (settings["general_instructions"], settings["archive_label"]) == ("I live in Utrecht.", "Mail/Old archive")
    audit = await owner.fetch("select version, channel from categories.list_audit order by 1")
    assert [(row["version"], row["channel"]) for row in audit] == [(1, "operator"), (2, "web")]


async def test_given_a_previous_version_without_settings_when_put_then_the_default_archive_label_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")], settings=False)

    response = await put(api, 1, [entry("Mine")], instructions="x")

    assert response.status_code == 200
    assert await owner.fetchval("select archive_label from categories.list_settings where version = 2") == ARCHIVE


@pytest.mark.parametrize("change", ["kind", "notify", "senders", "subdomains", "instructions"])
async def test_given_one_v2_field_changed_when_put_then_it_is_a_new_version(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    change: str,
) -> None:
    (invoices,) = await seed(
        owner,
        [("Invoices", "Bills")],
        details={0: {"senders": [("example.nl", True, False)]}},
        instructions="same",
    )
    fields: dict[str, Any] = {"kind": "topic", "notify": False, "senders": [sender("example.nl")]}
    instructions = "same"
    match change:
        case "kind":
            fields["kind"] = "extra"
        case "notify":
            fields["notify"] = True
        case "senders":
            fields["senders"] = [sender("example.nl"), sender("a@example.nl")]
        case "subdomains":
            fields["senders"] = [sender("example.nl", subdomains=True)]
        case _:
            instructions = "different"

    response = await put(api, 1, [entry("Invoices", "Bills", invoices, **fields)], instructions=instructions)

    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert await owner.fetchval(VERSIONS, MAILBOX) == 2


async def test_given_an_unchanged_v2_list_in_another_form_when_put_then_no_version_and_no_audit_record(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    stored_senders = [("example.nl", True, True), ("a@example.nl", False, False)]
    (invoices,) = await seed(
        owner,
        [("Invoices", "Bills")],
        details={0: {"kind": "extra", "notify": True, "senders": stored_senders}},
        instructions="Be brief.",
    )
    audits = await owner.fetchval("select count(*) from categories.list_audit")

    response = await put(
        api,
        1,
        [
            entry(
                "Invoices",
                "Bills",
                invoices,
                kind="extra",
                notify=True,
                senders=[sender(" A@EXAMPLE.nl "), sender("EXAMPLE.nl", subdomains=True)],
            )
        ],
        instructions=" Be brief. ",
    )

    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1
    assert await owner.fetchval("select count(*) from categories.list_audit") == audits


# Criterion 2 (U-label-structure-11): every rule violation, every problem, nothing stored
def _problem(rule: str, field: str, index: int | None, position: int | None = None, other: int | None = None) -> Any:
    return {"rule": rule, "field": field, "index": index, "position": position, "otherIndex": other}


async def test_given_sender_and_instruction_violations_when_put_then_422_lists_each_problem_with_its_field(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    categories = [
        entry("A", senders=[sender("gmail.com"), sender("*.example.nl")]),
        entry("B", senders=[sender("x.nl"), sender("X.nl", subdomains=True)]),
        entry("C", kind="extra", senders=[sender("x.nl")]),
        entry("", senders=[sender("y.nl")]),
    ]

    response = await put(api, 1, categories, instructions="g" * 4001)

    assert response.status_code == 422
    assert response.json()["problems"] == [
        _problem("name_empty", "name", 3),
        _problem("instructions_too_long", "instructions", None),
        _problem("sender_refused_domain", "senders", 0, 0),
        _problem("sender_invalid", "senders", 0, 1),
        _problem("sender_duplicate", "senders", 1, 1, 1),
    ]
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_a_duplicate_entry_in_two_topics_when_put_then_422_names_both_categories(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])

    response = await put(
        api, 1, [entry("A", senders=[sender("x.nl")]), entry("B", senders=[sender("X.NL", subdomains=True)])]
    )

    assert response.status_code == 422
    assert response.json()["problems"] == [_problem("sender_duplicate", "senders", 1, 0, 0)]


async def test_given_more_than_100_senders_in_a_category_when_put_then_422_sender_too_many(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])

    response = await put(api, 1, [entry("A", senders=[sender(f"s{n}@example.nl") for n in range(101)])])

    assert response.status_code == 422
    assert response.json()["problems"] == [_problem("sender_too_many", "senders", 0)]
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


# Criterion 4 (U-label-structure-11): the 409 carries the v2 list
async def test_given_a_stale_version_with_a_v2_body_when_put_then_409_carries_the_v2_current_list(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")], details={0: {"kind": "extra", "notify": True}}, instructions="Hi")

    response = await put(api, 0, [entry("Mine")])

    assert response.status_code == 409
    current = response.json()["current"]
    assert current["generalInstructions"] == "Hi"
    assert (current["categories"][0]["kind"], current["categories"][0]["notify"]) == ("extra", True)


# Criterion 5 (U-label-structure-11): the grants of the api role and no canary text
@pytest.mark.parametrize(
    "statement",
    [
        "update categories.category_sender set subdomains = true",
        "delete from categories.category_sender",
        "update categories.list_settings set general_instructions = 'x'",
        "update categories.list_settings set archive_label = 'x'",
        "delete from categories.list_settings",
        "update categories.category set kind = 'extra'",
        "delete from categories.category",
        "truncate categories.category_sender",
    ],
)
async def test_given_the_api_role_when_it_changes_or_removes_a_stored_list_then_42501(
    owner: asyncpg.Connection,  # noqa: F811
    web_database: Database,  # noqa: F811
    statement: str,
) -> None:
    await seed(owner, [("Invoices", "Bills")], details={0: {"senders": [("example.nl", True, False)]}})

    with pytest.raises(DBAPIError) as refused:
        async with web_database.session() as session, session.begin():
            await session.execute(text(statement))

    assert getattr(refused.value.orig, "sqlstate", None) == "42501"


CANARIES = ("canary-description-71", "canary-sender-71@example.nl", "canary-instructions-71", "canary-name-71")


async def test_given_the_database_refuses_the_write_when_put_then_500_and_no_response_or_log_carries_a_canary(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    await owner.execute(
        "alter table categories.category_sender add constraint ck_canary check (entry <> 'canary-sender-71@example.nl')"
    )
    caplog.set_level(logging.DEBUG)

    response = await put(
        api,
        1,
        [entry("canary-name-71", "canary-description-71", senders=[sender("canary-sender-71@example.nl")])],
        instructions="canary-instructions-71",
    )

    assert response.status_code == 500
    assert [c for c in CANARIES if c in response.text or c in caplog.text] == []
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_canary_text_in_refused_input_when_put_then_the_422_and_the_logs_carry_none_of_it(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    caplog.set_level(logging.DEBUG)

    response = await put(
        api,
        1,
        [entry("canary-name-71/", "", senders=[sender("canary-sender-71@@example.nl")])],
        instructions="canary-instructions-71" + "x" * 4000,
    )

    assert response.status_code == 422
    assert [c for c in CANARIES if c in response.text or c in caplog.text] == []


# Criterion 7 (U-label-structure-11): the maxima within a fixed time bound
TIME_BOUND_SECONDS = 20.0


async def test_given_100_categories_of_100_senders_when_saved_and_read_then_each_takes_under_the_time_bound(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    categories = [
        entry(
            f"Category {n}",
            "d" * 1500,
            kind="topic" if n % 2 else "extra",
            notify=bool(n % 3),
            senders=[sender(f"s{m}@host{n}.example.nl") for m in range(100)],
        )
        for n in range(100)
    ]

    started = time.monotonic()
    saved = await put(api, 1, categories, instructions="g" * 4000)
    saving = time.monotonic() - started
    started = time.monotonic()
    read = await get(api)
    reading = time.monotonic() - started

    assert saved.status_code == 200
    assert read.status_code == 200
    assert saved.json() == read.json()
    assert sum(len(c["senders"]) for c in read.json()["categories"]) == 10_000
    assert max(saving, reading) < TIME_BOUND_SECONDS
    assert await owner.fetchval("select count(*) from categories.category_sender where version = 2") == 10_000


# Criteria 1 to 3
async def test_given_a_nested_name_the_limits_and_100_categories_when_put_then_it_is_accepted_and_stored_trimmed(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    categories = [entry(" Huis / Energie ", "d" * 1500), entry("y" * 40 + "/" + "z" * 40)]
    categories += [entry(f"C{n}") for n in range(98)]

    response = await put(api, 1, categories)

    assert response.status_code == 200
    names = [c["name"] for c in response.json()["categories"]]
    assert len(names) == 100
    assert names[0] == "Huis/Energie"
    assert len(response.json()["categories"][0]["description"]) == 1500


async def test_given_a_label_of_225_characters_when_put_then_it_is_accepted(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    name = "/".join(["x" * 40] * 5 + ["y" * 14])  # 5 * 41 + 14 = 219, plus "Assistant/" is 229: trim to 225
    name = name[: 225 - len("Assistant/")]

    response = await put(api, 1, [entry(name)])

    assert response.status_code == 200


# Criterion 5
def _item(
    name: str, description: str, *, kind: str = "topic", senders: list[SenderItem] | None = None
) -> CategoryInput:
    return CategoryInput(name=name, description=description, kind=Kind(kind), notify=False, senders=senders or [])


def _stored(labels: list[str], adoptable: list[str], existing: list[str]) -> StoredList:
    adopted = {label.casefold() for label in adoptable}
    owned = [label for label in labels if label.casefold() not in adopted and label.startswith("Assistant/")]
    names = [*existing, *(label.removeprefix("Assistant/") for label in owned)]
    categories = tuple(StoredCategory(uuid.uuid4(), name, "x", Kind.TOPIC, notify=False, senders=()) for name in names)
    return StoredList(1, categories, "", ARCHIVE, {}, {}, tuple(labels))


def _fill(description: str) -> str:
    return "d" * int(description.strip("_")) if description.startswith("__") else description


def _nested(name: str) -> str:
    if not name.startswith("__label_len_"):
        return name
    length = int(name.removeprefix("__label_len_").removesuffix("__")) - len("Assistant/")
    parts: list[str] = []
    while length > 0:
        parts.append("a" * min(40, length))
        length -= min(40, length) + 1
    return "/".join(parts)


@pytest.mark.parametrize("case", CASES["category"], ids=[c["id"] for c in CASES["category"]])
def test_given_a_shared_category_case_when_the_api_checks_the_list_then_the_rules_match(case: dict[str, Any]) -> None:
    items = [_item(name, "x") for name in case["existing"]]
    items.append(_item(_nested(case["name"]), _fill(case["description"])))
    stored = _stored(case["labels"], case["adoptable"], [])

    problems = problems_of(items, "", stored)

    assert [p.rule for p in problems if p.index == len(items) - 1] == case["rules"]


@pytest.mark.parametrize("case", CASES["list"], ids=[c["id"] for c in CASES["list"]])
def test_given_a_shared_list_case_when_the_api_checks_the_list_then_the_problems_match(case: dict[str, Any]) -> None:
    if "generate" in case:
        items = [_item(f"Category {i}", "x") for i in range(case["generate"])]
    else:
        items = [_item(c["name"], c["description"]) for c in case["categories"]]
    stored = _stored(case["labels"], case["adoptable"], [])

    problems = problems_of(items, "", stored)

    assert [[p.index, p.rule] for p in problems] == case["problems"]


# Criterion 6
def test_given_the_backend_when_read_then_nothing_names_a_removed_rule() -> None:
    removed = ["name_" + "too_long", "name_" + "slash"]  # built in pieces so this file does not match itself
    root = Path(__file__).resolve().parents[1]
    sources = [*(root / "app").rglob("*.py"), *(root / "tests").rglob("*.py")]

    assert [(path.name, rule) for path in sources for rule in removed if rule in path.read_text("utf-8")] == []


@pytest.mark.parametrize("case", CASES["instructions"], ids=[c["id"] for c in CASES["instructions"]])
def test_given_a_shared_instructions_case_when_the_api_checks_the_list_then_the_rules_match(
    case: dict[str, Any],
) -> None:
    problems = problems_of([], "g" * case["length"], _stored([], [], []))

    assert [p.rule for p in problems] == case["rules"]
    assert all(p.field == "instructions" and p.index is None for p in problems)


@pytest.mark.parametrize("case", SENDER_CASES["validate"], ids=[c["id"] for c in SENDER_CASES["validate"]])
def test_given_a_shared_sender_case_when_the_api_checks_the_list_then_the_problems_match(case: dict[str, Any]) -> None:
    items = [
        _item(
            c["name"],
            "x",
            kind=c["kind"],
            senders=[SenderItem(entry=e["text"], subdomains=e["subdomains"]) for e in c["entries"]],
        )
        for c in case["categories"]
    ]
    if "generate_entries" in case:
        items[0] = _item(
            items[0].name,
            "x",
            kind=items[0].kind.value,
            senders=[SenderItem(entry=f"s{i}@example.nl", subdomains=False) for i in range(case["generate_entries"])],
        )

    problems = problems_of(items, "", _stored([], [], []))

    assert [[p.rule, p.index, p.position, p.other_index] for p in problems] == case["problems"]
    assert all(p.field == "senders" for p in problems)


async def test_given_a_name_that_is_an_older_category_when_put_then_it_is_adopted_not_refused(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    (invoices,) = await seed(owner, [("Invoices", "Bills")])
    await label(owner, "Assistant/Invoices")
    await label(owner, "Assistant/Old stuff")

    response = await put(api, 1, [entry("Invoices", id_=invoices), entry("old STUFF")])

    assert response.status_code == 200


async def test_given_a_name_whose_label_belongs_to_a_category_still_on_the_list_when_put_then_it_is_refused(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    (invoices,) = await seed(owner, [("Invoices", "Bills")])
    await label(owner, "Assistant/Invoices")

    response = await put(api, 1, [entry("Bills", id_=invoices), entry("Invoices")])

    assert response.status_code == 422
    assert _problem("name_label_exists", "name", 1) in response.json()["problems"]


async def test_given_a_duplicate_id_when_put_then_422_id_duplicate(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    (invoices,) = await seed(owner, [("Invoices", "Bills")])

    response = await put(api, 1, [entry("A", id_=invoices), entry("B", id_=invoices)])

    assert response.status_code == 422
    assert _problem("id_duplicate", "id", 1) in response.json()["problems"]


async def test_given_the_empty_list_when_put_then_other_stays_and_cannot_be_deleted_or_renamed(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    await count(owner, NIL, 4)

    emptied = await put(api, 1, [])
    renamed = await request(api, "PUT", {**body_of(2, []), "other": {"name": "Rest"}})

    assert emptied.status_code == 200
    assert emptied.json()["categories"] == []
    assert emptied.json()["other"] == {"mailCount": 4}
    assert renamed.status_code == 422
    assert await owner.fetchval(VERSIONS, MAILBOX) == 2


@pytest.mark.parametrize(
    "body",
    [
        {**body_of(1, [entry("A")]), "extra": 1},
        body_of(1, [{**entry("A"), "position": 3}]),
        body_of(-1, []),
        {"categories": [], "generalInstructions": ""},
        {"version": 1, "generalInstructions": ""},
        {"version": 1, "categories": []},
        {"version": 1, "categories": [], "generalInstructions": None},
        body_of(1, [{**entry("A"), "name": 5}]),
        body_of(1, [entry("A", id_="not-a-uuid")]),
        body_of(1, [{**entry("A"), "kind": "label"}]),
        body_of(1, [{**entry("A"), "notify": "yes"}]),
        body_of(1, [{**entry("A"), "senders": [{"entry": "a.nl"}]}]),
        body_of(1, [{**entry("A"), "senders": [{"entry": "a.nl", "subdomains": False, "x": 1}]}]),
        body_of(1, [{k: v for k, v in entry("A").items() if k != "kind"}]),
        body_of(1, [{k: v for k, v in entry("A").items() if k != "notify"}]),
        body_of(1, [{k: v for k, v in entry("A").items() if k != "senders"}]),
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
        content='{"version": 0, "categories": [], "generalInstructions": ""}',
        headers={
            "Content-Type": "text/plain",
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
            "Cookie": f"{COOKIE_NAME}={value}",
        },
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
    # The fake clock starts when the module is imported, the versions carry the database's clock of a later moment:
    # moving it by a whole day keeps the test independent of how long the run took so far.
    api.app.state.clock.advance(timedelta(days=1))

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

    response = await request(api, method, body_of(1, []) if method == "PUT" else None, cookie=False)

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
        json=body_of(1, []) if method == "PUT" else None,
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
            "Cookie": f"{COOKIE_NAME}={value}",
        },
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
