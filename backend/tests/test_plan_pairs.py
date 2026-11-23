# ruff: noqa: F811
# pyright: reportUnusedImport=false
"""U-label-structure-39: the review plan shows pairs, confidence, tips and what moved on its own (ADR-0056).

Plans, items and requests are seeded as the owner of the schema (the agent writes them in production); the routes are
called as the web role. The review plan stays the one the routes act on.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import asyncpg

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
    GENERIC_409,
    MAILBOX,
    NIL,
    SENDER_CANARY,
    SUBJECT_CANARY,
    Api,
    api,
    approve_body,
    call,
    decide,
    seed_plan,
    set_apply_config,
)

TOPIC_SHOP = uuid.UUID(int=101)
EXTRA_ORDERS = uuid.UUID(int=102)
TOPIC_WORK = uuid.UUID(int=103)
EXTRA_INVOICE = uuid.UUID(int=104)
NAMES = {
    TOPIC_SHOP: ("Shopping", "topic"),
    EXTRA_ORDERS: ("Shopping/Orders", "extra"),
    TOPIC_WORK: ("Work/Projects", "topic"),
    EXTRA_INVOICE: ("Work/Projects/Invoices", "extra"),
}
ZERO_AUTO = {"moved": 0, "scheduled": 0, "skipped": 0}
Pair = tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]


@dataclass(frozen=True)
class Review:
    plan_id: uuid.UUID
    item_ids: list[int]


async def seed_names(owner: asyncpg.Connection) -> None:
    """Version 1 of the list: the categories the pairs point at."""
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)
    async with owner.transaction():
        await owner.execute("insert into categories.list_version (mailbox_id, version) values ($1, 1)", MAILBOX)
        for position, (cid, (name, kind)) in enumerate(NAMES.items()):
            await owner.execute(
                "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", MAILBOX, cid
            )
            await owner.execute(
                "insert into categories.category (mailbox_id, version, id, name, description, position, kind, notify) "
                "values ($1, 1, $2, $3, '', $4, $5, false)",
                MAILBOX,
                cid,
                name,
                position,
                kind,
            )


async def seed_request(owner: asyncpg.Connection, threshold: int = 80) -> uuid.UUID:
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)
    value = await owner.fetchval(
        "insert into categories.resort_request (mailbox_id, threshold) values ($1, $2) returning id",
        MAILBOX,
        threshold,
    )
    return uuid.UUID(str(value))


async def seed_kind_plan(
    owner: asyncpg.Connection, kind: str, request: uuid.UUID | None, state: str = "ready", moved: int = 0
) -> uuid.UUID:
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)
    plan_id = uuid.uuid4()
    await owner.execute(
        "insert into categories.plan (mailbox_id, id, list_version, state, cap, kind, request_id, moved_count) "
        "values ($1, $2, 1, $3, 5000, $4, $5, $6)",
        MAILBOX,
        plan_id,
        state,
        kind,
        request,
        moved,
    )
    return plan_id


async def seed_item(  # noqa: PLR0913  # one switch per column a test varies
    owner: asyncpg.Connection,
    plan_id: uuid.UUID,
    tag: str,
    *,
    pair: Pair = (None, None, None, None),
    confidence: int | None = None,
    tip: str | None = None,
    state: str = "pending",
) -> int:
    decision = "pending" if state == "pending" else ("rejected" if state == "rejected" else "approved")
    item = await owner.fetchval(
        "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
        "old_category_id, new_category_id, old_topic_id, old_extra_id, new_topic_id, new_extra_id, confidence_pct, "
        "tip, decision, state) values ($1, $2, $3, 'Sender', $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15) "
        "returning id",
        MAILBOX,
        plan_id,
        tag,
        SENDER_CANARY,
        SUBJECT_CANARY,
        NIL,
        CAT_A,
        *pair,
        confidence,
        tip,
        decision,
        state,
    )
    return int(str(item))


async def items_of(api: Api) -> list[dict[str, Any]]:
    response = await call(api, "GET", "/api/plan/items")
    assert response.status_code == 200
    return list(response.json()["items"])


async def seed_review_with_two_items(owner: asyncpg.Connection, request: uuid.UUID) -> Review:
    review = await seed_kind_plan(owner, "review", request)
    ids = [
        await seed_item(owner, review, f"r{i}", pair=(None, None, TOPIC_SHOP, None), confidence=40) for i in range(2)
    ]
    return Review(review, ids)


# Criterion 1
async def test_given_a_review_plan_with_pairs_when_items_are_read_then_the_full_names_of_topic_and_extra_come_back(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_names(owner)
    plan = await seed_kind_plan(owner, "review", None)
    await seed_item(owner, plan, "a", pair=(TOPIC_SHOP, EXTRA_ORDERS, TOPIC_WORK, EXTRA_INVOICE))
    await seed_item(owner, plan, "b", pair=(None, None, TOPIC_SHOP, None))

    first, second = await items_of(api)

    assert (first["oldTopic"], first["oldExtra"]) == ("Shopping", "Shopping/Orders")
    assert (first["newTopic"], first["newExtra"]) == ("Work/Projects", "Work/Projects/Invoices")
    assert (second["oldTopic"], second["oldExtra"]) == (None, None)
    assert (second["newTopic"], second["newExtra"]) == ("Shopping", None)


async def test_given_an_item_without_a_pair_when_read_then_every_new_field_is_null(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_plan(owner, moves=((NIL, CAT_A),))

    (item,) = await items_of(api)

    assert [item[k] for k in ("oldTopic", "oldExtra", "newTopic", "newExtra", "confidencePct", "tip")] == [None] * 6


async def test_given_two_plans_of_one_request_when_items_are_read_then_only_the_review_plan_items_come_back(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_names(owner)
    request = await seed_request(owner)
    auto = await seed_kind_plan(owner, "auto", request, state="scheduled")
    review = await seed_kind_plan(owner, "review", request)
    await seed_item(owner, auto, "x", pair=(None, None, TOPIC_WORK, None), state="approved")
    await seed_item(owner, review, "y", pair=(None, None, TOPIC_SHOP, None))

    items = await items_of(api)
    plan = (await call(api, "GET", "/api/plan")).json()

    assert [i["newTopic"] for i in items] == ["Shopping"]
    assert plan["id"] == str(review)
    assert plan["counts"]["items"] == 1
    assert plan["state"] == "ready"


# Criterion 2
async def test_given_items_with_a_confidence_and_a_tip_when_read_then_both_come_back_as_stored(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_names(owner)
    plan = await seed_kind_plan(owner, "review", None)
    await seed_item(owner, plan, "a", pair=(None, None, TOPIC_SHOP, None), confidence=62, tip="Looks like a receipt.")
    await seed_item(owner, plan, "b", pair=(None, None, TOPIC_SHOP, None))

    first, second = await items_of(api)

    assert (first["confidencePct"], first["tip"]) == (62, "Looks like a receipt.")
    assert (second["confidencePct"], second["tip"]) == (None, None)


# Criterion 3
async def test_given_an_auto_plan_when_the_plan_is_read_then_threshold_and_counts_of_the_auto_plan_come_back(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    request = await seed_request(owner, 80)
    auto = await seed_kind_plan(owner, "auto", request, state="applying", moved=7)
    await seed_kind_plan(owner, "review", request)
    for index, state in enumerate(("applied", "applied", "approved", "approved", "approved", "skipped", "failed")):
        await seed_item(owner, auto, f"a{index}", confidence=90, state=state)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["threshold"] == 80
    assert body["auto"] == {"moved": 9, "scheduled": 3, "skipped": 1}


async def test_given_an_applied_auto_plan_when_the_plan_is_read_then_its_moved_count_is_the_moved_number(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    request = await seed_request(owner, 60)
    await seed_kind_plan(owner, "auto", request, state="applied", moved=12)
    await seed_kind_plan(owner, "review", request)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["auto"] == {"moved": 12, "scheduled": 0, "skipped": 0}


async def test_given_an_auto_plan_of_another_request_when_the_plan_is_read_then_it_is_not_counted(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    mine = await seed_request(owner, 70)
    other = await seed_request(owner, 90)
    await seed_kind_plan(owner, "auto", other, state="applied", moved=5)
    await seed_kind_plan(owner, "review", mine)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["threshold"] == 70
    assert body["auto"] == ZERO_AUTO


# Criterion 4
async def test_given_a_review_plan_without_an_auto_plan_when_read_then_the_summary_says_zero(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    request = await seed_request(owner, 75)
    await seed_kind_plan(owner, "review", request)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["threshold"] == 75
    assert body["auto"] == ZERO_AUTO


async def test_given_an_old_plan_without_a_request_when_read_then_the_threshold_is_null_and_the_summary_zero(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed_plan(owner)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["threshold"] is None
    assert body["auto"] == ZERO_AUTO


# Criterion 5
async def test_given_a_tip_with_markup_and_a_link_when_read_then_the_text_is_returned_unchanged_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    tip = '<b>Add sender</b> <a href="https://evil.example/x">click</a> [x](https://evil.example) &amp; "q"'
    plan = await seed_kind_plan(owner, "review", None)
    await seed_item(owner, plan, "a", tip=tip)
    before = await owner.fetch("select * from categories.plan_item order by id")
    senders_before = await owner.fetchval("select count(*) from categories.category_sender")

    (item,) = await items_of(api)

    assert item["tip"] == tip
    assert await owner.fetch("select * from categories.plan_item order by id") == before
    assert await owner.fetchval("select count(*) from categories.category_sender") == senders_before


# Criterion 6
async def test_given_a_review_and_an_auto_plan_when_decisions_and_approve_are_used_then_the_contracts_are_unchanged(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await set_apply_config(owner)
    await seed_names(owner)
    request = await seed_request(owner)
    auto = await seed_kind_plan(owner, "auto", request, state="scheduled")
    await seed_item(owner, auto, "x", pair=(None, None, TOPIC_WORK, None), confidence=95, state="approved")
    seeded = await seed_review_with_two_items(owner, request)

    decided = await call(api, "POST", "/api/plan/decisions", decide(seeded, {"all": True}))  # type: ignore[arg-type]
    wrong = await call(api, "POST", "/api/plan/decisions", decide(seeded, {"all": True}, count=99))  # type: ignore[arg-type]
    approved = await call(api, "POST", "/api/plan/approve", approve_body(seeded))  # type: ignore[arg-type]

    assert (decided.status_code, decided.json()) == (200, {"changed": 2})
    assert (wrong.status_code, wrong.json()) == (409, GENERIC_409)
    assert approved.status_code == 200
    assert set(approved.json()) == {"state", "applyAfter"}
    assert approved.json()["state"] == "scheduled"
    assert await owner.fetchval("select state from categories.plan where id = $1", auto) == "scheduled"


async def test_given_an_applied_plan_when_move_back_is_used_then_the_contract_is_unchanged(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    request = await seed_request(owner)
    applied = await seed_kind_plan(owner, "review", request, state="applied", moved=1)

    response = await call(api, "POST", f"/api/plan/{applied}/move-back")

    assert (response.status_code, response.json()) == (200, {"planId": str(applied), "processed": False})


# Criterion 7
async def test_given_pairs_and_tips_when_any_route_but_the_items_route_answers_then_sender_and_subject_are_not_in_it(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await set_apply_config(owner)
    await seed_names(owner)
    request = await seed_request(owner)
    auto = await seed_kind_plan(owner, "auto", request, state="applied", moved=1)
    await seed_item(owner, auto, "x", pair=(None, None, TOPIC_WORK, None), confidence=95, state="applied")
    seeded = await seed_review_with_two_items(owner, request)

    texts = [
        (await call(api, "POST", "/api/plan/decisions", decide(seeded, {"all": True}))).text,  # type: ignore[arg-type]
        (await call(api, "POST", "/api/plan/approve", approve_body(seeded))).text,  # type: ignore[arg-type]
        (await call(api, "POST", f"/api/plan/{auto}/move-back")).text,
    ]

    summary = (await call(api, "GET", "/api/plan")).json()
    texts.append(str(summary["auto"]) + str(summary["threshold"]))  # the plan route shows its group example (ADR-0044)

    for text in texts:
        assert SENDER_CANARY not in text
        assert SUBJECT_CANARY not in text
