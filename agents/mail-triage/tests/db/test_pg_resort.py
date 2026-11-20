"""U-mail-categories-22, criteria 1 and 2: the plan build on the real database, as the agent role (ADR-0046, ADR-0043).

Every test acts as the agent role, so the grants are part of what is tested. Two stores on two sessions stand for two
agent processes.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from app.core.resort_plan import PlanState
from app.db.pg_resort import PgBuildStore
from app.usecases.resort_build import ItemDraft
from tests.db.resort_support import MAILBOX, OTHER_ID, agent_sessions, seed_list

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]  # the fixture is used by name

CAP = 50


def _draft(message_id: str, new_category: str) -> ItemDraft:
    return ItemDraft(
        message_id, "Sender", "sender@example.test", "A subject", uuid.UUID(OTHER_ID), uuid.UUID(new_category)
    )


async def _building_plan(store: PgBuildStore, owner: asyncpg.Connection) -> tuple[uuid.UUID, str]:
    category = (await seed_list(owner, ["Finance"]))[0]
    plan = await store.create_plan(1, CAP)
    assert plan is not None
    return plan.plan_id, category


async def test_given_no_list_when_it_is_read_then_version_0_and_given_a_list_then_its_latest_version_in_order(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    assert (await store.current_list()).version == 0

    ids = await seed_list(cat_owner, ["Finance", "Travel"], version=1)
    ids2 = await seed_list(cat_owner, ["Travel", "Finance", "Home"], version=2)
    current = await store.current_list()

    assert current.version == 2
    assert [c.category_id for c in current.categories] == ids2
    assert [c.name for c in current.categories] == ["Travel", "Finance", "Home"]
    assert current.categories[0].description == "about Travel"
    assert ids != ids2


async def test_given_a_building_plan_when_progress_is_written_then_item_counts_and_cursor_change_together(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _building_plan(store, cat_owner)

    assert await store.record_progress(plan_id, item=_draft("m1", category), cursor="c1", checked=1, unclear=0)
    assert await store.record_progress(plan_id, item=None, cursor="c2", checked=0, unclear=1)
    assert await store.record_progress(plan_id, item=None, cursor="c3", checked=1, unclear=0)

    plan = await store.latest_plan()
    assert plan is not None
    assert (plan.state, plan.cursor, plan.checked, plan.unclear, plan.items, plan.cap) == (
        PlanState.BUILDING,
        "c3",
        2,
        1,
        1,
        CAP,
    )
    row = await cat_owner.fetchrow("select sender_name, subject, decision, state from categories.plan_item")
    assert row is not None
    assert (row["sender_name"], row["subject"], row["decision"], row["state"]) == (
        "Sender",
        "A subject",
        "pending",
        "pending",
    )


async def test_given_the_same_mail_listed_twice_when_progress_is_written_then_one_item_stays(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _building_plan(store, cat_owner)

    assert await store.record_progress(plan_id, item=_draft("m1", category), cursor="c1", checked=1, unclear=0)
    assert await store.record_progress(plan_id, item=_draft("m1", category), cursor="c2", checked=1, unclear=0)

    assert await cat_owner.fetchval("select count(*) from categories.plan_item") == 1


async def test_given_a_replaced_plan_when_progress_is_written_then_it_is_refused_and_no_item_is_added(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _building_plan(store, cat_owner)
    assert await store.record_progress(plan_id, item=_draft("m1", category), cursor="c1", checked=1, unclear=0)

    assert await store.replace_plan(plan_id)

    assert await cat_owner.fetchval("select count(*) from categories.plan_item") == 0  # the items went with the plan
    assert not await store.record_progress(plan_id, item=_draft("m2", category), cursor="c2", checked=1, unclear=0)
    assert await cat_owner.fetchval("select count(*) from categories.plan_item") == 0
    assert not await store.replace_plan(plan_id)  # a second replace changes nothing
    assert (await store.latest_plan()) is not None
    assert (await store.latest_plan()).state is PlanState.REPLACED  # type: ignore[union-attr]


async def test_given_an_open_plan_when_another_is_created_then_none_and_after_it_ended_a_new_one_comes(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, _category = await _building_plan(store, cat_owner)

    assert await store.create_plan(1, CAP) is None

    await store.replace_plan(plan_id)
    newer = await store.create_plan(1, CAP)

    assert newer is not None
    assert newer.plan_id != plan_id
    latest = await store.latest_plan()
    assert latest is not None
    assert latest.plan_id == newer.plan_id


async def test_given_two_agent_processes_when_both_complete_the_same_plan_then_exactly_one_wins(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    first, second = PgBuildStore(agent_sessions, MAILBOX), PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _building_plan(first, cat_owner)
    await first.record_progress(plan_id, item=_draft("m1", category), cursor="c1", checked=1, unclear=0)

    results = await asyncio.gather(
        first.complete_build(plan_id, not_looked_at=7), second.complete_build(plan_id, not_looked_at=9)
    )

    assert sorted(results) == [False, True]
    assert await cat_owner.fetchval("select state from categories.plan") == "ready"
    assert await cat_owner.fetchval("select not_looked_at from categories.plan") in {7, 9}
    assert not await first.record_progress(plan_id, item=None, cursor="c9", checked=1, unclear=0)  # no more progress


async def test_given_a_replace_and_a_complete_at_once_then_exactly_one_wins_and_a_replaced_plan_keeps_no_item(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    first, second = PgBuildStore(agent_sessions, MAILBOX), PgBuildStore(agent_sessions, MAILBOX)
    plan_id, category = await _building_plan(first, cat_owner)
    await first.record_progress(plan_id, item=_draft("m1", category), cursor="c1", checked=1, unclear=0)

    completed, replaced = await asyncio.gather(
        first.complete_build(plan_id, not_looked_at=0), second.replace_plan(plan_id)
    )

    state = await cat_owner.fetchval("select state from categories.plan")
    items = await cat_owner.fetchval("select count(*) from categories.plan_item")
    # complete first, then replace (a ready plan is replaced too): both true; replace first: complete refused
    assert (completed, replaced, state, items) in {(True, True, "replaced", 0), (False, True, "replaced", 0)}


async def test_given_estimate_and_rejections_when_read_back_then_they_match_per_list_version_and_mailbox(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgBuildStore(agent_sessions, MAILBOX)
    plan_id, _category = await _building_plan(store, cat_owner)
    await cat_owner.execute("insert into categories.mailbox (id) values ('other') on conflict do nothing")
    await cat_owner.execute(
        "insert into categories.rejection (mailbox_id, message_id, list_version) values "
        "('mb1', 'r1', 1), ('mb1', 'r2', 2), ('other', 'r3', 1)"
    )

    await store.record_estimate(plan_id, 321)

    assert await cat_owner.fetchval("select estimate_total from categories.plan") == 321
    assert await store.rejected_ids(1) == frozenset({"r1"})
    assert await store.rejected_ids(2) == frozenset({"r2"})
    assert await PgBuildStore(agent_sessions, "other").latest_plan() is None  # another mailbox sees none of it
