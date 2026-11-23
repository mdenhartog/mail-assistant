"""U-label-structure-23, criteria 1, 5 and 7 on the real database, as the agent role (ADR-0056).

The build store makes a ``review`` and an ``auto`` plan of one request, routes each item into the plan it belongs to at
insert time (the agent has no right to move or delete items), approves the ``auto`` plan through ``approve_system_plan``
and counts that approval toward the rolling 24 hours.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.core.resort_plan import PlanKind, PlanState
from app.db.pg_approval import PgApprovalStore
from app.db.pg_resort import PgBuildStore
from app.usecases.resort_build import ItemDraft, ResortRequest
from tests.db.plan_support import set_apply_config
from tests.db.resort_support import MAILBOX, OTHER_ID, agent_sessions, seed_list

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]

CAP = 50


def _draft(message_id: str, new_category: str, confidence: int) -> ItemDraft:
    return ItemDraft(
        message_id,
        "Sender",
        "sender@example.test",
        "A subject",
        uuid.UUID(OTHER_ID),
        None,
        uuid.UUID(new_category),
        None,
        confidence,
    )


async def _request(owner: asyncpg.Connection, threshold: int) -> ResortRequest:
    request_id = uuid.uuid4()
    await owner.execute(
        "insert into categories.resort_request (mailbox_id, id, threshold) values ($1, $2, $3)",
        MAILBOX,
        request_id,
        threshold,
    )
    return ResortRequest(request_id, threshold)


async def _started(store: PgBuildStore, owner: asyncpg.Connection, threshold: int = 80) -> tuple[uuid.UUID, str]:
    category = (await seed_list(owner, ["Finance"]))[0]
    await set_apply_config(owner, MAILBOX, threshold=1000, delay_minutes=15)
    plan = await store.start_plan(await _request(owner, threshold), 1, CAP)
    assert plan is not None
    return plan.plan_id, category


async def _write(  # noqa: PLR0913, PLR0917 - a test helper that names one item
    store: PgBuildStore, plan_id: uuid.UUID, category: str, message_id: str, confidence: int, kind: PlanKind
) -> None:
    assert await store.record_progress(
        plan_id, item=_draft(message_id, category, confidence), kind=kind, cursor=message_id, checked=1, unclear=0
    )


async def _plans(owner: asyncpg.Connection) -> dict[str, Any]:
    rows = await owner.fetch("select id, kind, state, threshold, request_id from categories.plan")
    return {r["kind"]: r for r in rows}


async def test_given_a_request_when_the_plan_starts_then_a_review_and_an_auto_plan_copy_its_threshold(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)

    plan_id, _ = await _started(store, cat_owner, 80)

    plans = await _plans(cat_owner)
    assert set(plans) == {"review", "auto"}
    assert plans["review"]["id"] == plan_id
    assert {p["state"] for p in plans.values()} == {"building"}
    assert {p["threshold"] for p in plans.values()} == {80}
    assert plans["auto"]["request_id"] == plans["review"]["request_id"]
    latest = await store.latest_plan()
    assert latest is not None
    assert (latest.plan_id, latest.threshold) == (plan_id, 80)  # the record stands for the review plan


async def test_given_items_of_95_80_and_79_at_threshold_80_when_written_then_each_goes_into_its_own_plan(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _started(store, cat_owner, 80)

    await _write(store, plan_id, category, "m95", 95, PlanKind.AUTO)
    await _write(store, plan_id, category, "m80", 80, PlanKind.AUTO)
    await _write(store, plan_id, category, "m79", 79, PlanKind.REVIEW)

    rows = await cat_owner.fetch(
        "select p.kind, i.message_id from categories.plan_item i join categories.plan p on p.id = i.plan_id"
    )
    assert {(r["kind"], r["message_id"]) for r in rows} == {("auto", "m95"), ("auto", "m80"), ("review", "m79")}
    latest = await store.latest_plan()
    assert latest is not None
    assert (latest.items, latest.auto_items, latest.checked) == (1, 2, 3)


async def test_given_a_finished_build_when_completed_then_the_auto_plan_is_approved_by_the_system(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _started(store, cat_owner, 80)
    await _write(store, plan_id, category, "m1", 95, PlanKind.AUTO)
    await _write(store, plan_id, category, "m2", 60, PlanKind.REVIEW)

    assert await store.complete_build(plan_id, not_looked_at=0)

    plans = await _plans(cat_owner)
    assert (plans["auto"]["state"], plans["review"]["state"]) == ("scheduled", "ready")
    items = await cat_owner.fetch(
        "select p.kind, i.decision, i.decision_source from categories.plan_item i "
        "join categories.plan p on p.id = i.plan_id"
    )
    assert {(r["kind"], r["decision"], r["decision_source"]) for r in items} == {
        ("auto", "approved", "threshold"),
        ("review", "pending", "user"),
    }  # nothing below the threshold is approved
    assert await cat_owner.fetchval("select count(*) from categories.plan_approval") == 1
    assert not await store.complete_build(plan_id, not_looked_at=0)  # a second caller does nothing


async def test_given_a_build_without_an_auto_item_when_completed_then_the_empty_auto_plan_is_dropped(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _started(store, cat_owner, 90)
    await _write(store, plan_id, category, "m1", 60, PlanKind.REVIEW)

    assert await store.complete_build(plan_id, not_looked_at=0)

    plans = await _plans(cat_owner)
    assert (plans["auto"]["state"], plans["review"]["state"]) == ("replaced", "ready")
    assert await cat_owner.fetchval("select count(*) from categories.plan_approval") == 0


async def test_given_a_plan_under_construction_when_replaced_then_both_plans_go_and_their_items_with_them(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _started(store, cat_owner)
    await _write(store, plan_id, category, "m1", 95, PlanKind.AUTO)

    assert await store.replace_plan(plan_id)

    assert {p["state"] for p in (await _plans(cat_owner)).values()} == {"replaced"}
    assert await cat_owner.fetchval("select count(*) from categories.plan_item") == 0
    assert not await store.record_progress(plan_id, item=None, kind=PlanKind.REVIEW, cursor="c", checked=1, unclear=0)


async def test_given_a_scheduled_auto_plan_when_the_review_plan_is_replaced_then_the_auto_plan_stays(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _started(store, cat_owner)
    await _write(store, plan_id, category, "m1", 95, PlanKind.AUTO)
    await store.complete_build(plan_id, not_looked_at=0)

    assert await store.replace_plan(plan_id)  # a list save replaces the pending review plan

    plans = await _plans(cat_owner)
    assert (plans["auto"]["state"], plans["review"]["state"]) == ("scheduled", "replaced")
    assert await cat_owner.fetchval("select count(*) from categories.plan_item") == 1


async def test_given_earlier_approvals_when_the_system_approves_then_it_counts_toward_the_24_hour_wait(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _started(store, cat_owner)
    await set_apply_config(cat_owner, MAILBOX, threshold=2, delay_minutes=15)
    await cat_owner.execute(  # a user approval of 2 mails an hour ago
        "insert into categories.plan_approval (mailbox_id, plan_id, approved_count, channel, actor_digest, at) "
        "values ($1, gen_random_uuid(), 2, 'web', repeat('c', 64), now() - interval '1 hour')",
        MAILBOX,
    )
    await _write(store, plan_id, category, "m1", 95, PlanKind.AUTO)

    await store.complete_build(plan_id, not_looked_at=0)  # 2 + 1 > 2: the wait applies

    after = await cat_owner.fetchval("select apply_after - now() from categories.plan where kind = 'auto'")
    assert isinstance(after, timedelta)
    assert timedelta(minutes=14) < after <= timedelta(minutes=15)
    assert (await _plans(cat_owner))["auto"]["state"] == PlanState.SCHEDULED.value
    assert await cat_owner.fetchval("select sum(approved_count) from categories.plan_approval") == 3


async def test_given_a_delayed_system_plan_when_announced_then_the_notice_knows_its_kind_and_the_review_items(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _started(store, cat_owner, 80)
    await set_apply_config(cat_owner, MAILBOX, threshold=1, delay_minutes=15)
    await _write(store, plan_id, category, "m1", 95, PlanKind.AUTO)
    await _write(store, plan_id, category, "m2", 99, PlanKind.AUTO)
    await _write(store, plan_id, category, "m3", 60, PlanKind.REVIEW)
    await store.complete_build(plan_id, not_looked_at=0)  # 2 > 1: delayed

    [announced] = await PgApprovalStore(agent_sessions, MAILBOX).unannounced()

    assert (announced.kind, announced.mail_count, announced.waiting_review) == (PlanKind.AUTO, 2, 1)
