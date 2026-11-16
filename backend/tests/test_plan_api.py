# pyright: reportUnusedImport=false
"""U-mail-categories-17: the plan routes against a real PostgreSQL, called as the web role.

Plans, items and the apply configuration are seeded as the owner of the schema (the agent writes them in production);
the decisions, the approval and the move-back request are made through the API and read back as the owner.
"""

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from tests.fakes import FakeClock, make_app, make_settings, real_minute

T0 = real_minute()
CSRF_KEY = b"b" * 32
ORIGIN = "https://settings.example.test"
USER = username_digest(b"k" * 32, "canary-user")
MAILBOX = "primary"
OTHER_MAILBOX = "second"
NIL = uuid.UUID(int=0)
CAT_A = uuid.UUID(int=1)
CAT_B = uuid.UUID(int=2)
CAT_C = uuid.UUID(int=3)
GENERIC_401 = {"type": "about:blank", "title": "Unauthorized", "status": 401}
GENERIC_403 = {"type": "about:blank", "title": "Forbidden", "status": 403}
GENERIC_409 = {"type": "about:blank", "title": "Conflict", "status": 409}
DEFAULT_MOVES = ((NIL, CAT_A), (NIL, CAT_A), (NIL, CAT_B), (CAT_A, CAT_B), (CAT_B, CAT_C))
SENDER_CANARY = "sender-canary-7731@example.test"
SUBJECT_CANARY = "subject canary 9482"
NOV1 = datetime.fromisoformat("2026-11-01T00:00:00+00:00")
OPEN_STATES = ("building", "ready", "scheduled", "applying")


@dataclass
class Api:
    http: AsyncClient
    app: FastAPI
    store: SessionStore


@dataclass(frozen=True)
class Seeded:
    plan_id: uuid.UUID
    item_ids: list[int]


@pytest.fixture
async def api(web_database: Database) -> AsyncIterator[Api]:  # noqa: F811
    clock = FakeClock(T0)
    store = SessionStore(web_database, SecretsIdSource(), SecurityEvents(web_database, clock, b"e" * 32))
    app = make_app(make_settings(categories_mailbox_id=MAILBOX, rate_limit_per_minute=100_000))
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, SecurityEvents(web_database, clock, b"e" * 32))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Api(http, app, store)


async def seed_plan(  # noqa: PLR0913  # one switch per column a test varies
    owner: asyncpg.Connection,  # noqa: F811
    *,
    mailbox: str = MAILBOX,
    state: str = "ready",
    moves: tuple[tuple[uuid.UUID, uuid.UUID], ...] = DEFAULT_MOVES,
    checked: int = 0,
    cap: int = 5000,
    unclear: int = 0,
    estimate: int | None = None,
    not_looked_at: int = 0,
    terminal_at: datetime | None = None,
    tag: str = "m",
) -> Seeded:
    """Insert a plan in ``state`` with one item per move, as the agent would."""
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", mailbox)
    plan_id = uuid.uuid4()
    await owner.execute(
        "insert into categories.plan (mailbox_id, id, list_version, state, checked_count, cap, unclear_count, "
        "estimate_total, not_looked_at, terminal_at) values ($1, $2, 1, $3, $4, $5, $6, $7, $8, $9)",
        mailbox,
        plan_id,
        state,
        checked,
        cap,
        unclear,
        estimate,
        not_looked_at,
        terminal_at,
    )
    item_ids: list[int] = []
    for index, (old, new) in enumerate(moves):
        item_id = await owner.fetchval(
            "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
            "old_category_id, new_category_id) values ($1, $2, $3, $4, $5, $6, $7, $8) returning id",
            mailbox,
            plan_id,
            f"{tag}{index}",
            f"Sender {index}",
            SENDER_CANARY if index == 0 else f"sender{index}@example.test",
            SUBJECT_CANARY if index == 0 else f"Subject {index}",
            old,
            new,
        )
        item_ids.append(int(str(item_id)))
    return Seeded(plan_id, item_ids)


async def set_apply_config(owner: asyncpg.Connection, *, threshold: int = 50, delay: int = 15) -> None:  # noqa: F811
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)
    await owner.execute(
        "insert into categories.apply_config (mailbox_id, threshold, delay_minutes) values ($1, $2, $3) "
        "on conflict (mailbox_id) do update set threshold = excluded.threshold, delay_minutes = excluded.delay_minutes",
        MAILBOX,
        threshold,
        delay,
    )


async def call(  # noqa: PLR0913  # one switch per part of the request that a test may leave out
    api: Api,
    method: str,
    path: str,
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
    if cookie:
        headers["Cookie"] = f"{COOKIE_NAME}={value}"
    return await api.http.request(method, path, json=body, headers=headers)


def decide(
    plan: Seeded, scope: dict[str, Any], *, count: int | None = None, decision: str = "approved"
) -> dict[str, Any]:
    return {
        "planId": str(plan.plan_id),
        "itemCount": len(plan.item_ids) if count is None else count,
        "scope": scope,
        "decision": decision,
    }


def approve_body(plan: Seeded, *, count: int | None = None) -> dict[str, Any]:
    return {"planId": str(plan.plan_id), "itemCount": len(plan.item_ids) if count is None else count}


async def decisions_of(owner: asyncpg.Connection, plan: Seeded) -> list[str]:  # noqa: F811
    rows = await owner.fetch("select decision from categories.plan_item where plan_id = $1 order by id", plan.plan_id)
    return [row["decision"] for row in rows]


# Criterion 1
async def test_given_a_ready_plan_when_get_then_state_groups_counts_and_the_last_applied_plan_are_returned(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)
    applied = await seed_plan(
        owner, state="applied", moves=(), terminal_at=datetime.fromisoformat("2026-11-12T10:00:00+00:00")
    )
    await seed_plan(owner, mailbox=OTHER_MAILBOX, moves=((NIL, CAT_C),), tag="o")

    response = await call(api, "GET", "/api/plan")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(plan.plan_id)
    assert body["state"] == "ready"
    assert body["applyAfter"] is None
    assert body["counts"] == {"items": 5, "pending": 5, "approved": 0, "rejected": 0}
    assert (
        body["groups"]
        == [
            {"from": str(NIL), "to": str(CAT_A), "count": 2},
            {"from": str(CAT_A), "to": str(CAT_B), "count": 1},
            {"from": str(CAT_B), "to": str(CAT_C), "count": 1},
            {"from": str(NIL), "to": str(CAT_B), "count": 1},
        ]
        or sorted(body["groups"], key=lambda g: (-g["count"], g["from"], g["to"])) == body["groups"]
    )
    assert sum(group["count"] for group in body["groups"]) == 5
    assert body["lastPlan"] == {
        "id": str(applied.plan_id),
        "state": "applied",
        "appliedAt": "2026-11-12T10:00:00Z",
        "movedCount": 0,
    }


async def test_given_a_plan_being_built_when_get_then_the_progress_is_returned_and_nothing_is_decidable_yet(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(
        owner, state="building", moves=((NIL, CAT_A),), checked=340, cap=5000, unclear=7, estimate=1200, not_looked_at=0
    )

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["state"] == "building"
    assert body["progress"] == {"checked": 340, "cap": 5000, "unclear": 7, "estimate": 1200, "notLookedAt": 0}


# U-mail-categories-24, criterion 1 (AC-43)
async def test_given_a_plan_past_the_cap_when_get_then_progress_holds_the_estimate_and_the_not_looked_at_number(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner, moves=((NIL, CAT_A),), checked=5000, cap=5000, unclear=3, estimate=7400, not_looked_at=2400)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["progress"] == {"checked": 5000, "cap": 5000, "unclear": 3, "estimate": 7400, "notLookedAt": 2400}


async def test_given_a_plan_without_an_estimate_when_get_then_the_estimate_is_null(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner, state="building", moves=((NIL, CAT_A),), checked=10)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["progress"]["estimate"] is None
    assert body["progress"]["notLookedAt"] == 0


# U-mail-categories-24, criterion 3 (AC-13)
async def test_given_groups_approved_in_different_sessions_when_get_then_each_group_holds_its_exact_approved_count(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)
    group = {"group": {"from": str(NIL), "to": str(CAT_A)}, "groupCount": 2}
    assert (await call(api, "POST", "/api/plan/decisions", decide(plan, group))).status_code == 200
    ids = {"ids": [plan.item_ids[2]]}
    assert (await call(api, "POST", "/api/plan/decisions", decide(plan, ids))).status_code == 200

    groups = {(g["from"], g["to"]): g for g in (await call(api, "GET", "/api/plan")).json()["groups"]}

    assert groups[(str(NIL), str(CAT_A))]["approved"] == 2
    assert groups[(str(NIL), str(CAT_B))]["approved"] == 1
    assert groups[(str(CAT_A), str(CAT_B))]["approved"] == 0
    assert groups[(str(CAT_B), str(CAT_C))]["approved"] == 0


async def test_given_a_scheduled_plan_when_get_then_apply_after_and_the_decision_counts_are_returned(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)
    await owner.execute(
        "update categories.plan_item set decision = 'approved', state = 'approved' where id = any($1)",
        plan.item_ids[:3],
    )
    await owner.execute(
        "update categories.plan_item set decision = 'rejected', state = 'rejected' where id = any($1)",
        plan.item_ids[3:4],
    )
    await owner.execute(
        "update categories.plan set state = 'scheduled', apply_after = '2026-11-15T12:30:00+00' where id = $1",
        plan.plan_id,
    )

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["state"] == "scheduled"
    assert body["applyAfter"] == "2026-11-15T12:30:00Z"
    assert body["counts"] == {"items": 5, "pending": 1, "approved": 3, "rejected": 1}


async def test_given_no_plan_when_get_then_the_state_is_null_and_there_is_nothing_to_show(api: Api) -> None:
    response = await call(api, "GET", "/api/plan")

    assert response.status_code == 200
    assert response.json() == {
        "id": None,
        "state": None,
        "progress": {"checked": 0, "cap": 0, "unclear": 0, "estimate": None, "notLookedAt": 0},
        "groups": [],
        "counts": {"items": 0, "pending": 0, "approved": 0, "rejected": 0},
        "applyAfter": None,
        "applyThreshold": None,
        "applyDelayMinutes": None,
        "lastPlan": None,
    }


async def test_given_two_applied_plans_when_get_then_the_last_plan_is_the_one_applied_most_recently(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner, state="applied", moves=(), terminal_at=datetime.fromisoformat("2026-11-01T10:00:00+00:00"))
    newer = await seed_plan(
        owner, state="applied", moves=(), terminal_at=datetime.fromisoformat("2026-11-10T10:00:00+00:00")
    )
    await seed_plan(owner, state="replaced", moves=(), terminal_at=datetime.fromisoformat("2026-11-14T10:00:00+00:00"))

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["lastPlan"]["id"] == str(newer.plan_id)


# Criterion 2
async def test_given_150_items_when_get_items_by_page_then_at_most_100_per_page_as_text_with_no_store(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner, moves=tuple((NIL, CAT_A) for _ in range(150)))

    first = await call(api, "GET", "/api/plan/items?page=1")
    second = await call(api, "GET", "/api/plan/items?page=2")

    assert first.status_code == second.status_code == 200
    assert len(first.json()["items"]) == 100
    assert first.json()["hasMore"] is True
    assert len(second.json()["items"]) == 50
    assert second.json()["hasMore"] is False
    ids = [item["id"] for item in first.json()["items"] + second.json()["items"]]
    assert len(set(ids)) == 150
    for response in (first, second):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-type"] == "application/json"


async def test_given_an_item_when_get_items_then_sender_name_address_subject_and_state_are_returned_not_the_message_id(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner, moves=((NIL, CAT_A),))

    item = (await call(api, "GET", "/api/plan/items")).json()["items"][0]

    assert set(item) == {
        "id",
        "senderName",
        "senderAddress",
        "subject",
        "from",
        "to",
        "decision",
        "state",
        "reason",
    }
    assert item["senderName"] == "Sender 0"
    assert item["senderAddress"] == SENDER_CANARY
    assert item["subject"] == SUBJECT_CANARY
    assert (item["from"], item["to"]) == (str(NIL), str(CAT_A))
    assert (item["decision"], item["state"], item["reason"]) == ("pending", "pending", None)


async def test_given_markup_in_sender_and_subject_when_get_items_then_it_is_returned_as_text(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner, moves=((NIL, CAT_A),))
    await owner.execute(
        "update categories.plan_item set sender_name = '<b>Bank</b>', subject = '<script>alert(1)</script>' "
        "where id = $1",
        plan.item_ids[0],
    )

    response = await call(api, "GET", "/api/plan/items")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json()["items"][0]["senderName"] == "<b>Bank</b>"
    assert response.json()["items"][0]["subject"] == "<script>alert(1)</script>"


async def test_given_a_group_filter_when_get_items_then_only_that_group_is_returned(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner)

    response = await call(api, "GET", f"/api/plan/items?from={NIL}&to={CAT_A}")

    assert [(i["from"], i["to"]) for i in response.json()["items"]] == [(str(NIL), str(CAT_A))] * 2


async def test_given_a_sender_in_the_query_when_get_items_then_it_is_not_a_filter(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner)

    response = await call(api, "GET", "/api/plan/items?sender=nobody@example.test&subject=none&q=none")

    assert len(response.json()["items"]) == 5


async def test_given_a_plan_of_another_mailbox_when_get_items_then_none_of_its_items_are_returned(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner, mailbox=OTHER_MAILBOX, tag="o")

    response = await call(api, "GET", "/api/plan/items")

    assert response.json() == {"items": [], "page": 1, "hasMore": False}


@pytest.mark.parametrize("query", ["page=0", "page=-1", "page=101", "page=x", "from=not-a-uuid", "to=1"])
async def test_given_a_bad_page_or_filter_when_get_items_then_422_without_the_input(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    query: str,
) -> None:
    await seed_plan(owner)

    response = await call(api, "GET", f"/api/plan/items?{query}")

    assert response.status_code == 422
    assert response.json() == {"type": "about:blank", "title": "Unprocessable content", "status": 422}


# Criterion 3
async def test_given_the_right_plan_id_and_count_when_a_decision_is_posted_then_it_is_recorded(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, {"all": True}))

    assert response.status_code == 200
    assert response.json() == {"changed": 5}
    assert await decisions_of(owner, plan) == ["approved"] * 5
    audit = await owner.fetchrow("select scope, item_count, decision, channel from categories.plan_decision")
    assert audit is not None
    assert tuple(audit.values()) == ("all", 5, "approved", "web")


async def test_given_a_group_scope_when_a_decision_is_posted_then_only_that_group_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)
    scope = {"group": {"from": str(NIL), "to": str(CAT_A)}, "groupCount": 2}

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, scope, decision="rejected"))

    assert response.status_code == 200
    assert response.json() == {"changed": 2}
    assert await decisions_of(owner, plan) == ["rejected", "rejected", "pending", "pending", "pending"]


async def test_given_an_ids_scope_when_a_decision_is_posted_then_only_those_items_change(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, {"ids": plan.item_ids[1:3]}))

    assert response.status_code == 200
    assert response.json() == {"changed": 2}
    assert await decisions_of(owner, plan) == ["pending", "approved", "approved", "pending", "pending"]


async def test_given_a_stale_plan_id_when_a_decision_is_posted_then_409_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)
    body = {**decide(plan, {"all": True}), "planId": str(uuid.uuid4())}

    response = await call(api, "POST", "/api/plan/decisions", body)

    assert response.status_code == 409
    assert response.json() == GENERIC_409
    assert await decisions_of(owner, plan) == ["pending"] * 5
    assert await owner.fetchval("select count(*) from categories.plan_decision") == 0


@pytest.mark.parametrize("count", [0, 4, 6])
async def test_given_a_stale_item_count_when_a_decision_is_posted_then_409_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    count: int,
) -> None:
    plan = await seed_plan(owner)

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, {"all": True}, count=count))

    assert response.status_code == 409
    assert response.json() == GENERIC_409
    assert await decisions_of(owner, plan) == ["pending"] * 5


async def test_given_a_group_that_changed_when_a_decision_is_posted_then_409_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)
    scope = {"group": {"from": str(NIL), "to": str(CAT_A)}, "groupCount": 3}

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, scope))

    assert response.status_code == 409
    assert await decisions_of(owner, plan) == ["pending"] * 5


async def test_given_an_id_of_another_plan_when_a_decision_is_posted_then_409_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner, tag="a")
    foreign = await seed_plan(owner, state="applied", tag="b", terminal_at=NOV1)

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, {"ids": [foreign.item_ids[0]]}))

    assert response.status_code == 409
    assert await decisions_of(owner, plan) == ["pending"] * 5
    assert await decisions_of(owner, foreign) == ["pending"] * 5


@pytest.mark.parametrize("state", ["building", "scheduled"])
async def test_given_a_plan_that_is_not_ready_when_a_decision_is_posted_then_409(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    state: str,
) -> None:
    plan = await seed_plan(owner, state=state)

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, {"all": True}))

    assert response.status_code == 409
    assert await decisions_of(owner, plan) == ["pending"] * 5


async def test_given_a_plan_of_another_mailbox_when_a_decision_is_posted_then_409_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner, mailbox=OTHER_MAILBOX, tag="o")

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, {"all": True}))

    assert response.status_code == 409
    assert await decisions_of(owner, plan) == ["pending"] * 5


@pytest.mark.parametrize(
    "body",
    [
        {"planId": "x", "itemCount": 5, "scope": {"all": True}, "decision": "approved"},
        {"itemCount": 5, "scope": {"all": True}, "decision": "approved"},
        {"planId": str(uuid.uuid4()), "itemCount": -1, "scope": {"all": True}, "decision": "approved"},
        {"planId": str(uuid.uuid4()), "itemCount": 5, "scope": {"all": False}, "decision": "approved"},
        {"planId": str(uuid.uuid4()), "itemCount": 5, "scope": {}, "decision": "approved"},
        {"planId": str(uuid.uuid4()), "itemCount": 5, "scope": {"all": True, "ids": [1]}, "decision": "approved"},
        {"planId": str(uuid.uuid4()), "itemCount": 5, "scope": {"ids": []}, "decision": "approved"},
        {"planId": str(uuid.uuid4()), "itemCount": 5, "scope": {"ids": [0]}, "decision": "approved"},
        {"planId": str(uuid.uuid4()), "itemCount": 5, "scope": {"ids": ["1"]}, "decision": "approved"},
        {"planId": str(uuid.uuid4()), "itemCount": 5, "scope": {"all": True}, "decision": "pending"},
        {"planId": str(uuid.uuid4()), "itemCount": 5, "scope": {"all": True}, "decision": "approved", "extra": 1},
    ],
)
async def test_given_a_malformed_decision_when_posted_then_422_without_the_input(
    api: Api, body: dict[str, Any]
) -> None:
    response = await call(api, "POST", "/api/plan/decisions", body)

    assert response.status_code == 422
    assert response.json() == {"type": "about:blank", "title": "Unprocessable content", "status": 422}


# Criterion 4
async def test_given_more_than_200_ids_when_a_decision_is_posted_then_it_is_refused_with_a_reason_and_nothing_changes(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner, moves=tuple((NIL, CAT_A) for _ in range(250)))

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, {"ids": plan.item_ids[:201]}))

    assert response.status_code == 422
    assert response.json() == {
        "type": "about:blank",
        "title": "Unprocessable content",
        "status": 422,
        "reason": "too_many_ids",
    }
    assert set(await decisions_of(owner, plan)) == {"pending"}


async def test_given_exactly_200_ids_when_a_decision_is_posted_then_they_are_accepted(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner, moves=tuple((NIL, CAT_A) for _ in range(250)))

    response = await call(api, "POST", "/api/plan/decisions", decide(plan, {"ids": plan.item_ids[:200]}))

    assert response.status_code == 200
    assert response.json() == {"changed": 200}


async def test_given_200_ids_of_the_largest_size_when_posted_then_the_body_fits_the_default_body_limit(
    api: Api,
) -> None:
    ids = [999_999_999_999_999_000 + number for number in range(200)]
    body = {"planId": str(uuid.uuid4()), "itemCount": 1, "scope": {"ids": ids}, "decision": "approved"}

    response = await call(api, "POST", "/api/plan/decisions", body)

    assert response.status_code == 409  # a valid body that names no plan of ours, not a 413


# Criterion 5
async def test_given_a_ready_plan_when_approved_then_it_is_scheduled_for_now_and_pending_items_are_rejected(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await set_apply_config(owner, threshold=50)
    plan = await seed_plan(owner)
    await call(api, "POST", "/api/plan/decisions", decide(plan, {"ids": plan.item_ids[:3]}))

    response = await call(api, "POST", "/api/plan/approve", approve_body(plan))

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "scheduled"
    applies = datetime.fromisoformat(body["applyAfter"])
    assert abs(applies - datetime.now(tz=applies.tzinfo)) < timedelta(minutes=1)
    assert await decisions_of(owner, plan) == ["approved"] * 3 + ["rejected"] * 2
    assert await owner.fetchval("select state from categories.plan where id = $1", plan.plan_id) == "scheduled"


async def test_given_an_approval_above_the_threshold_when_approved_then_apply_after_is_the_delay_away(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await set_apply_config(owner, threshold=2, delay=15)
    plan = await seed_plan(owner)
    await call(api, "POST", "/api/plan/decisions", decide(plan, {"all": True}))

    body = (await call(api, "POST", "/api/plan/approve", approve_body(plan))).json()

    applies = datetime.fromisoformat(body["applyAfter"])
    wait = applies - datetime.now(tz=applies.tzinfo)
    assert timedelta(minutes=14) < wait < timedelta(minutes=16)


async def test_given_a_repeated_approve_when_posted_then_the_same_state_and_apply_after_come_back(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await set_apply_config(owner, threshold=2, delay=15)
    plan = await seed_plan(owner)
    await call(api, "POST", "/api/plan/decisions", decide(plan, {"all": True}))
    first = await call(api, "POST", "/api/plan/approve", approve_body(plan))

    second = await call(api, "POST", "/api/plan/approve", approve_body(plan))

    assert second.status_code == 200
    assert second.json() == first.json()
    assert await owner.fetchval("select count(*) from categories.plan_approval") == 1


@pytest.mark.parametrize("which", ["id", "count"])
async def test_given_a_stale_plan_id_or_count_when_approved_then_409_and_nothing_is_approved(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    which: str,
) -> None:
    await set_apply_config(owner)
    plan = await seed_plan(owner)
    body = {**approve_body(plan), "planId": str(uuid.uuid4())} if which == "id" else approve_body(plan, count=4)

    response = await call(api, "POST", "/api/plan/approve", body)

    assert response.status_code == 409
    assert response.json() == GENERIC_409
    assert await owner.fetchval("select state from categories.plan where id = $1", plan.plan_id) == "ready"
    assert await owner.fetchval("select count(*) from categories.plan_approval") == 0
    assert await decisions_of(owner, plan) == ["pending"] * 5


@pytest.mark.parametrize("state", ["building", "applying", "applied", "replaced"])
async def test_given_a_plan_that_is_not_ready_when_approved_then_409(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    state: str,
) -> None:
    await set_apply_config(owner)
    plan = await seed_plan(
        owner,
        state=state,
        terminal_at=None if state in OPEN_STATES else NOV1,
    )

    response = await call(api, "POST", "/api/plan/approve", approve_body(plan))

    assert response.status_code == 409


async def test_given_no_apply_settings_when_approved_then_409_and_nothing_is_approved(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)

    response = await call(api, "POST", "/api/plan/approve", approve_body(plan))

    assert response.status_code == 409
    assert await decisions_of(owner, plan) == ["pending"] * 5


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"planId": "x", "itemCount": 5},
        {"planId": str(uuid.uuid4()), "itemCount": -1},
        {"planId": str(uuid.uuid4())},
    ],
)
async def test_given_a_malformed_approve_when_posted_then_422(api: Api, body: dict[str, Any]) -> None:
    response = await call(api, "POST", "/api/plan/approve", body)

    assert response.status_code == 422
    assert response.json() == {"type": "about:blank", "title": "Unprocessable content", "status": 422}


# Criterion 6
async def test_given_an_applied_plan_when_move_back_then_one_request_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner, state="applied", moves=(), terminal_at=NOV1)

    first = await call(api, "POST", f"/api/plan/{plan.plan_id}/move-back")
    second = await call(api, "POST", f"/api/plan/{plan.plan_id}/move-back")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"planId": str(plan.plan_id), "processed": False}
    rows = await owner.fetch("select mailbox_id, plan_id, processed, actor_digest from categories.move_back_request")
    assert [(row["mailbox_id"], row["plan_id"], row["processed"]) for row in rows] == [(MAILBOX, plan.plan_id, False)]
    assert len(rows[0]["actor_digest"]) == 64


@pytest.mark.parametrize("kind", ["unknown", "ready", "other-mailbox"])
async def test_given_a_plan_that_is_not_an_applied_plan_of_this_mailbox_when_move_back_then_409_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    kind: str,
) -> None:
    ready = await seed_plan(owner)
    foreign = await seed_plan(
        owner,
        mailbox=OTHER_MAILBOX,
        state="applied",
        moves=(),
        terminal_at=NOV1,
        tag="o",
    )
    target = {"unknown": uuid.uuid4(), "ready": ready.plan_id, "other-mailbox": foreign.plan_id}[kind]

    response = await call(api, "POST", f"/api/plan/{target}/move-back")

    assert response.status_code == 409
    assert response.json() == GENERIC_409
    assert await owner.fetchval("select count(*) from categories.move_back_request") == 0


async def test_given_a_plan_id_that_is_not_a_uuid_when_move_back_then_422(api: Api) -> None:
    response = await call(api, "POST", "/api/plan/not-a-uuid/move-back")

    assert response.status_code == 422


# Criterion 7
ROUTES = [
    ("GET", "/api/plan", None),
    ("GET", "/api/plan/items", None),
    (
        "POST",
        "/api/plan/decisions",
        {"planId": str(uuid.uuid4()), "itemCount": 1, "scope": {"all": True}, "decision": "approved"},
    ),
    ("POST", "/api/plan/approve", {"planId": str(uuid.uuid4()), "itemCount": 1}),
    ("POST", f"/api/plan/{uuid.uuid4()}/move-back", None),
]
WRITES = [route for route in ROUTES if route[0] == "POST"]


async def _nothing_written(owner: asyncpg.Connection, plan: Seeded) -> None:  # noqa: F811
    assert await decisions_of(owner, plan) == ["pending"] * 5
    for table in ("plan_decision", "plan_approval", "move_back_request"):
        assert await owner.fetchval(f"select count(*) from categories.{table}") == 0  # noqa: S608  # fixed names


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
async def test_given_no_session_when_called_then_the_generic_401_with_no_store(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    method: str,
    path: str,
    body: Any,
) -> None:
    plan = await seed_plan(owner)

    response = await call(api, method, path, body, cookie=False)

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    assert response.headers["cache-control"] == "no-store"
    await _nothing_written(owner, plan)


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
async def test_given_the_web_lock_when_called_then_the_generic_401_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    method: str,
    path: str,
    body: Any,
) -> None:
    plan = await seed_plan(owner)
    value, created = await api.store.create(USER, T0)
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, $1)", T0)

    response = await api.http.request(
        method,
        path,
        json=body,
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
            "Cookie": f"{COOKIE_NAME}={value}",
        },
    )

    assert response.status_code == 401
    assert response.json() == GENERIC_401
    await _nothing_written(owner, plan)


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
@pytest.mark.parametrize(
    ("token", "origin", "extra"),
    [
        (False, ORIGIN, None),
        (True, None, None),
        (True, "https://evil.example.test", None),
        (False, None, None),
        (True, ORIGIN, {"Sec-Fetch-Site": "cross-site"}),
    ],
)
async def test_given_no_token_a_wrong_origin_or_a_cross_site_request_when_posted_then_the_generic_403(  # noqa: PLR0913, PLR0917  # one parameter per switch
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    method: str,
    path: str,
    body: Any,
    token: bool,
    origin: str | None,
    extra: dict[str, str] | None,
) -> None:
    plan = await seed_plan(owner)

    response = await call(api, method, path, body, token=token, origin=origin, extra_headers=extra)

    assert response.status_code == 403
    assert response.json() == GENERIC_403
    assert response.headers["cache-control"] == "no-store"
    await _nothing_written(owner, plan)


async def test_given_a_body_that_is_not_json_when_a_decision_is_posted_then_415(api: Api) -> None:
    value, created = await api.store.create(USER, T0)

    response = await api.http.post(
        "/api/plan/approve",
        content=b"planId=1",
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
            "Cookie": f"{COOKIE_NAME}={value}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    assert response.status_code == 415


async def test_given_a_state_mismatch_when_called_then_it_is_a_409_and_never_a_403(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner)

    statuses = {
        (await call(api, "POST", "/api/plan/decisions", decide(plan, {"all": True}, count=1))).status_code,
        (await call(api, "POST", "/api/plan/approve", approve_body(plan, count=1))).status_code,
        (await call(api, "POST", f"/api/plan/{plan.plan_id}/move-back")).status_code,
    }

    assert statuses == {409}


# Sender and subject stay out of logs, errors and the URL (MR-1, AC-30)
async def test_given_every_route_and_outcome_when_called_then_sender_and_subject_are_in_no_log_and_no_error_body(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await set_apply_config(owner)
    plan = await seed_plan(owner)
    applied = await seed_plan(owner, state="applied", moves=(), terminal_at=NOV1, tag="z")
    responses = [
        await call(api, "GET", "/api/plan"),
        await call(api, "GET", "/api/plan/items?page=0"),
        await call(api, "POST", "/api/plan/decisions", decide(plan, {"all": True}, count=9)),
        await call(api, "POST", "/api/plan/decisions", decide(plan, {"ids": [plan.item_ids[0]]})),
        await call(api, "POST", "/api/plan/approve", approve_body(plan, count=9)),
        await call(api, "POST", "/api/plan/approve", approve_body(plan)),
        await call(api, "POST", f"/api/plan/{uuid.uuid4()}/move-back"),
        await call(api, "POST", f"/api/plan/{applied.plan_id}/move-back"),
    ]

    errors = [response for response in responses if response.status_code >= 400]
    assert len(errors) >= 3
    for response in errors:
        assert SENDER_CANARY not in response.text
        assert SUBJECT_CANARY not in response.text
    text = " ".join(record.getMessage() for record in caplog.records)
    assert SENDER_CANARY not in text
    assert SUBJECT_CANARY not in text
    for response in responses:
        assert response.headers["cache-control"] == "no-store"


# U-mail-categories-24, criterion 5 (MR-1), rebuilt by U-mail-categories-32: the view shows one example mail per group
# (C-18), so the sender and subject of that mail are in the response; no other item is, and nothing reaches a log.
async def test_given_canary_strings_when_the_plan_is_read_then_only_the_examples_are_in_the_view_and_no_log(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    await seed_plan(owner, estimate=900, not_looked_at=4)
    caplog.set_level(logging.DEBUG)

    response = await call(api, "GET", "/api/plan")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert SENDER_CANARY in response.text  # the example of the first group
    assert "sender1@example.test" not in response.text  # not an example: the second item of a group of two
    assert "Subject 2" in response.text  # the example of the group that holds item 2
    logged = " ".join(record.getMessage() for record in caplog.records)
    for canary in (SENDER_CANARY, SUBJECT_CANARY):
        assert canary not in logged


# U-mail-categories-32, criterion 1 (C-18, AC-23): one example per group, the rejected count next to the approved one
async def test_given_groups_when_get_then_each_has_the_example_of_its_lowest_item_and_the_rejected_count(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    plan = await seed_plan(owner, moves=((NIL, CAT_A), (NIL, CAT_A), (NIL, CAT_A), (CAT_A, CAT_B)))
    await owner.execute(
        "update categories.plan_item set decision = 'approved', state = 'approved' where id = $1", plan.item_ids[1]
    )
    await owner.execute(
        "update categories.plan_item set decision = 'rejected', state = 'rejected' where id = any($1::bigint[])",
        [plan.item_ids[0], plan.item_ids[2]],
    )

    response = await call(api, "GET", "/api/plan")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    groups = {(g["from"], g["to"]): g for g in response.json()["groups"]}
    first = groups[(str(NIL), str(CAT_A))]
    assert first["count"] == 3
    assert (first["approved"], first["rejected"]) == (1, 2)
    assert first["example"] == {"senderName": "Sender 0", "senderAddress": SENDER_CANARY, "subject": SUBJECT_CANARY}
    second = groups[(str(CAT_A), str(CAT_B))]
    assert (second["approved"], second["rejected"]) == (0, 0)
    assert second["example"] == {
        "senderName": "Sender 3",
        "senderAddress": "sender3@example.test",
        "subject": "Subject 3",
    }


async def test_given_another_mailbox_when_get_then_its_items_are_never_an_example(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner, moves=((NIL, CAT_A),))
    await seed_plan(owner, mailbox=OTHER_MAILBOX, moves=((NIL, CAT_A),), tag="o")
    await owner.execute(
        "update categories.plan_item set subject = 'other mailbox subject' where mailbox_id = $1", OTHER_MAILBOX
    )

    response = await call(api, "GET", "/api/plan")

    assert "other mailbox subject" not in response.text


# U-mail-categories-32, criterion 2 (AC-30): the apply settings the approval uses, read only
async def test_given_the_apply_config_when_get_then_the_threshold_and_the_delay_are_in_the_view(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner)
    await set_apply_config(owner, threshold=40, delay=30)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["applyThreshold"] == 40
    assert body["applyDelayMinutes"] == 30


async def test_given_no_apply_config_when_get_then_the_settings_are_null(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await seed_plan(owner)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["applyThreshold"] is None
    assert body["applyDelayMinutes"] is None


async def test_given_no_plan_when_get_then_the_apply_settings_are_still_in_the_view(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await set_apply_config(owner, threshold=50, delay=15)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["state"] is None
    assert (body["applyThreshold"], body["applyDelayMinutes"]) == (50, 15)


# U-mail-categories-32, criterion 3 (C-18): "310 moved" survives the removal of the moved items
async def test_given_an_applied_plan_whose_items_are_gone_when_get_then_the_moved_count_is_the_stored_one(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    applied = await seed_plan(owner, state="applied", moves=(), terminal_at=NOV1)
    await owner.execute("update categories.plan set moved_count = 310 where id = $1", applied.plan_id)

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["lastPlan"]["movedCount"] == 310


async def test_given_an_applied_plan_whose_items_are_not_yet_removed_when_get_then_they_are_counted_too(
    api: Api,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    applied = await seed_plan(
        owner, state="applied", moves=((NIL, CAT_A), (NIL, CAT_A), (NIL, CAT_B)), terminal_at=NOV1
    )
    await owner.execute("update categories.plan set moved_count = 10 where id = $1", applied.plan_id)
    await owner.execute(
        "update categories.plan_item set decision = 'approved', state = 'applied' where id = any($1::bigint[])",
        applied.item_ids[:2],
    )

    body = (await call(api, "GET", "/api/plan")).json()

    assert body["lastPlan"]["movedCount"] == 12  # 10 stored, 2 applied items not yet removed; the skipped one is not
