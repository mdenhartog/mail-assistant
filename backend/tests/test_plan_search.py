# ruff: noqa: F811
# pyright: reportUnusedImport=false
"""U-mail-categories-35: the item search of the open plan (sender filter and sort) against a real PostgreSQL.

The sender text is personal data (ADR-0044, AC-30): it travels in a POST body, never in a URL, a log line or an error.
"""

import logging
import uuid
from typing import Any

import asyncpg
import pytest

from app.auth.cookies import COOKIE_NAME
from app.auth.csrf import csrf_token
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.test_plan_api import (  # noqa: F401  # the fixtures and helpers of the plan API tests
    CAT_A,
    CSRF_KEY,
    GENERIC_401,
    GENERIC_403,
    MAILBOX,
    NIL,
    ORIGIN,
    SENDER_CANARY,
    T0,
    USER,
    Api,
    api,
    call,
)

SEARCH = "/api/plan/items/search"
UNPROCESSABLE = {"type": "about:blank", "title": "Unprocessable content", "status": 422}
# Each mail is a name, an address and a subject.
MAIL = (
    ("Alice Jansen", "alice@shop.example.test", "Zebra offer"),
    ("Bob de Vries", "bob@bank.example.test", "Apple statement"),
    ("Carol", "ALICE.WORK@corp.example.test", "mango news"),
    ("100% Deals", "deals_x@promo.example.test", "Sale_now"),
    ("Dave O'Neil", "dave@x.example.test", "Hello"),
    ("Back\\slash", "slash@y.example.test", "Path"),
)


async def seed_mail(owner: asyncpg.Connection, mails: tuple[tuple[str, str, str], ...] = MAIL) -> list[int]:
    """An open plan whose items hold the given sender name, address and subject; returns the item ids."""
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)
    plan_id = uuid.uuid4()
    await owner.execute(
        "insert into categories.plan (mailbox_id, id, list_version, state, cap) values ($1, $2, 1, 'ready', 5000)",
        MAILBOX,
        plan_id,
    )
    ids: list[int] = []
    for index, (name, address, subject) in enumerate(mails):
        item_id = await owner.fetchval(
            "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
            "old_category_id, new_category_id) values ($1, $2, $3, $4, $5, $6, $7, $8) returning id",
            MAILBOX,
            plan_id,
            f"s{index}",
            name,
            address,
            subject,
            NIL,
            CAT_A,
        )
        ids.append(int(str(item_id)))
    return ids


async def search(api: Api, body: dict[str, Any]) -> Any:
    return await call(api, "POST", SEARCH, body)


def names(response: Any) -> list[str]:
    return [item["senderName"] for item in response.json()["items"]]


# Criterion 1
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("alice", ["Alice Jansen", "Carol"]),
        ("ALICE", ["Alice Jansen", "Carol"]),
        ("vries", ["Bob de Vries"]),
        ("bank.example", ["Bob de Vries"]),
        ("nobody", []),
    ],
)
async def test_given_a_sender_text_when_searched_then_only_items_with_it_in_name_or_address_come_back(
    api: Api,
    owner: asyncpg.Connection,
    text: str,
    expected: list[str],
) -> None:
    await seed_mail(owner)

    response = await search(api, {"sender": text})

    assert response.status_code == 200
    assert names(response) == expected
    assert response.headers["cache-control"] == "no-store"


async def test_given_a_sender_and_a_group_when_searched_then_both_filters_apply(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_mail(owner)

    hit = await search(api, {"sender": "alice", "from": str(NIL), "to": str(CAT_A)})
    miss = await search(api, {"sender": "alice", "from": str(CAT_A)})

    assert names(hit) == ["Alice Jansen", "Carol"]
    assert names(miss) == []


# Criterion 2
@pytest.mark.parametrize(
    ("sort", "order", "expected"),
    [
        ("sender", "asc", ["100% Deals", "Alice Jansen", "Back\\slash", "Bob de Vries", "Carol", "Dave O'Neil"]),
        ("sender", "desc", ["Dave O'Neil", "Carol", "Bob de Vries", "Back\\slash", "Alice Jansen", "100% Deals"]),
        ("subject", "asc", ["Bob de Vries", "Dave O'Neil", "Carol", "Back\\slash", "100% Deals", "Alice Jansen"]),
        ("subject", "desc", ["Alice Jansen", "100% Deals", "Back\\slash", "Carol", "Dave O'Neil", "Bob de Vries"]),
    ],
)
async def test_given_a_sort_when_searched_then_the_page_is_in_that_order_ignoring_case(
    api: Api,
    owner: asyncpg.Connection,
    sort: str,
    order: str,
    expected: list[str],
) -> None:
    await seed_mail(owner)

    response = await search(api, {"sort": sort, "order": order})

    assert names(response) == expected


async def test_given_equal_sort_keys_when_paged_then_every_item_appears_once_in_a_stable_order(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    ids = await seed_mail(owner, tuple(("Same", "same@example.test", "Same") for _ in range(150)))

    first = await search(api, {"sort": "sender", "order": "desc", "page": 1})
    second = await search(api, {"sort": "sender", "order": "desc", "page": 2})
    again = await search(api, {"sort": "sender", "order": "desc", "page": 1})

    seen = [item["id"] for item in first.json()["items"] + second.json()["items"]]
    assert sorted(seen) == ids
    assert first.json() == again.json()
    assert first.json()["hasMore"] is True
    assert second.json()["hasMore"] is False
    assert second.json()["page"] == 2


# Criterion 3
async def test_given_no_filter_and_no_sort_when_searched_then_the_answer_equals_the_get_answer(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_mail(owner)

    got = await call(api, "GET", "/api/plan/items")
    searched = await search(api, {})

    assert searched.status_code == 200
    assert searched.json() == got.json()
    assert len(searched.json()["items"]) == len(MAIL)


# Criterion 4
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("%", ["100% Deals"]),
        ("100%", ["100% Deals"]),
        ("_", ["100% Deals"]),
        ("e_n", []),
        ("s_x", ["100% Deals"]),
        ("s__x", []),
        ("\\", ["Back\\slash"]),
        ("'", ["Dave O'Neil"]),
        ("'; drop table categories.plan_item; --", []),
        ("%' or '1'='1", []),
    ],
)
async def test_given_wildcards_and_quotes_in_the_sender_text_when_searched_then_they_match_literally(
    api: Api,
    owner: asyncpg.Connection,
    text: str,
    expected: list[str],
) -> None:
    await seed_mail(owner)

    response = await search(api, {"sender": text})

    assert response.status_code == 200
    assert names(response) == expected
    assert await owner.fetchval("select count(*) from categories.plan_item") == len(MAIL)


# Criterion 5
async def test_given_the_canary_sender_text_when_searched_then_it_is_in_no_log_error_url_or_stored_row(
    api: Api,
    owner: asyncpg.Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await seed_mail(owner)
    canary = "canary-sender-5521"

    responses = [
        await search(api, {"sender": canary}),
        await search(api, {"sender": canary * 20}),
        await search(api, {"sender": canary, "sort": "bogus"}),
        await call(api, "POST", SEARCH, {"sender": canary}, cookie=False),
        await call(api, "POST", SEARCH, {"sender": canary}, token=False),
    ]

    assert [r.status_code for r in responses] == [200, 422, 422, 401, 403]
    for response in responses:
        assert canary not in response.text
        assert canary not in str(response.request.url)
        assert response.headers["cache-control"] == "no-store"
    text = " ".join(record.getMessage() for record in caplog.records)
    assert canary not in text
    for table in ("plan_item", "plan", "plan_decision", "plan_approval", "move_back_request"):
        rows = await owner.fetch(f"select t::text as row from categories.{table} t")  # noqa: S608  # fixed names
        assert not any(canary in row["row"] for row in rows)
    events = await owner.fetch("select e::text as row from web_auth.security_event e")
    assert not any(canary in row["row"] for row in events)


# Criterion 6
@pytest.mark.parametrize(
    "body",
    [
        {"sender": "x" * 101},
        {"sender": 5},
        {"sender": ["a"]},
        {"sort": "date"},
        {"sort": "SENDER"},
        {"order": "up"},
        {"page": 0},
        {"page": 101},
        {"from": "not-a-uuid"},
        {"extra": 1},
        {"sender": "a", "senderText": "b"},
    ],
)
async def test_given_a_sender_over_the_bound_or_an_unknown_value_when_searched_then_422_without_the_input(
    api: Api,
    owner: asyncpg.Connection,
    body: dict[str, Any],
) -> None:
    await seed_mail(owner)

    response = await search(api, body)

    assert response.status_code == 422
    assert response.json() == UNPROCESSABLE


async def test_given_a_sender_of_exactly_the_bound_when_searched_then_it_is_accepted(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_mail(owner)

    response = await search(api, {"sender": "x" * 100})

    assert response.status_code == 200
    assert names(response) == []


# Criterion 7
async def test_given_no_session_a_lock_or_no_token_when_searched_then_refused_as_the_other_plan_calls(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_mail(owner)

    no_session = await call(api, "POST", SEARCH, {}, cookie=False)
    no_token = await call(api, "POST", SEARCH, {}, token=False)
    wrong_origin = await call(api, "POST", SEARCH, {}, origin="https://evil.example.test")
    cross_site = await call(api, "POST", SEARCH, {}, extra_headers={"Sec-Fetch-Site": "cross-site"})

    assert no_session.status_code == 401
    assert no_session.json() == GENERIC_401
    assert {no_token.status_code, wrong_origin.status_code, cross_site.status_code} == {403}
    assert no_token.json() == GENERIC_403


async def test_given_the_web_lock_when_searched_then_the_generic_401(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_mail(owner)
    value, created = await api.store.create(USER, T0)
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", T0)

    response = await api.http.post(
        SEARCH,
        json={},
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
            "Cookie": f"{COOKIE_NAME}={value}",
        },
    )

    assert response.status_code == 401
    assert response.json() == GENERIC_401


async def test_given_a_body_that_is_not_json_when_searched_then_415(api: Api) -> None:
    value, created = await api.store.create(USER, T0)

    response = await api.http.post(
        SEARCH,
        content=b"sender=a",
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
            "Cookie": f"{COOKIE_NAME}={value}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    assert response.status_code == 415
