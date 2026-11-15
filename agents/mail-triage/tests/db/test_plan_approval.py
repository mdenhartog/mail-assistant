"""U-mail-categories-12, criteria 4, 5 and 7 (AC-13, AC-42, AC-47): ``categories.approve_plan``."""

from __future__ import annotations

import hashlib
from datetime import timedelta

import asyncpg
import pytest

from tests.db.conftest import API_ROLE
from tests.db.plan_support import (
    CAT_A,
    CAT_B,
    NIL,
    SeededPlan,
    scope_all,
    scope_ids,
    seed_plan,
    set_apply_config,
    sqlstate_of,
)

APPROVE = "select state, apply_after from categories.approve_plan($1, $2, $3)"
DECIDE = "select categories.record_decision($1, $2, $3, $4::jsonb, $5)"
DELAY = timedelta(minutes=15)


async def _approve(connection: asyncpg.Connection, plan: SeededPlan) -> asyncpg.Record:
    row = await connection.fetchrow(APPROVE, plan.mailbox, plan.plan_id, len(plan.item_ids))
    assert row is not None
    return row


async def _approve_all_items(connection: asyncpg.Connection, plan: SeededPlan) -> None:
    await connection.fetchval(DECIDE, plan.mailbox, plan.plan_id, len(plan.item_ids), scope_all(), "approved")


async def _offset(owner: asyncpg.Connection, apply_after: object) -> timedelta:
    """How far ``apply_after`` is from the database's now (the function and this query share the transaction clock
    only approximately, so tests compare with a tolerance)."""
    value = await owner.fetchval("select $1::timestamptz - now()", apply_after)
    assert isinstance(value, timedelta)
    return value


async def test_given_an_approval_at_or_below_the_threshold_when_it_is_made_then_the_plan_is_scheduled_for_now(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=5, delay_minutes=15)
    plan = await seed_plan(cat_owner)  # five items: exactly the threshold
    await _approve_all_items(cat_api, plan)

    row = await _approve(cat_api, plan)

    assert row["state"] == "scheduled"
    assert abs(await _offset(cat_owner, row["apply_after"])) < timedelta(minutes=1)
    stored = await cat_owner.fetchrow("select state, apply_after from categories.plan where id = $1", plan.plan_id)
    assert stored is not None
    assert (stored["state"], stored["apply_after"]) == (row["state"], row["apply_after"])


async def test_given_an_approval_above_the_threshold_when_it_is_made_then_the_apply_waits_the_delay(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=4, delay_minutes=15)
    plan = await seed_plan(cat_owner)
    await _approve_all_items(cat_api, plan)

    row = await _approve(cat_api, plan)

    assert row["state"] == "scheduled"
    assert abs(await _offset(cat_owner, row["apply_after"]) - DELAY) < timedelta(minutes=1)


async def test_given_the_delay_in_the_config_when_it_changes_then_the_function_follows_it_and_no_argument_can(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=1, delay_minutes=40)
    plan = await seed_plan(cat_owner)
    await _approve_all_items(cat_api, plan)

    row = await _approve(cat_api, plan)

    assert abs(await _offset(cat_owner, row["apply_after"]) - timedelta(minutes=40)) < timedelta(minutes=1)


async def test_given_two_approvals_of_49_within_24_hours_when_the_second_is_made_then_it_waits(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=50, delay_minutes=15)
    moves = ((NIL, CAT_A),) * 49
    first = await seed_plan(cat_owner, moves=moves, tag="a")
    await _approve_all_items(cat_api, first)
    first_row = await _approve(cat_api, first)
    await cat_owner.execute("update categories.plan set state = 'applying' where id = $1", first.plan_id)
    await cat_owner.execute("update categories.plan set state = 'applied' where id = $1", first.plan_id)
    second = await seed_plan(cat_owner, moves=moves, tag="b")
    await _approve_all_items(cat_api, second)

    second_row = await _approve(cat_api, second)

    assert abs(await _offset(cat_owner, first_row["apply_after"])) < timedelta(minutes=1)
    assert abs(await _offset(cat_owner, second_row["apply_after"]) - DELAY) < timedelta(minutes=1)


async def test_given_an_earlier_approval_older_than_24_hours_when_a_plan_is_approved_then_it_does_not_count(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=50, delay_minutes=15)
    moves = ((NIL, CAT_A),) * 49
    first = await seed_plan(cat_owner, moves=moves, tag="a")
    await _approve_all_items(cat_api, first)
    await _approve(cat_api, first)
    await cat_owner.execute("update categories.plan set state = 'applying' where id = $1", first.plan_id)
    await cat_owner.execute("update categories.plan set state = 'applied' where id = $1", first.plan_id)
    await cat_owner.execute("update categories.plan_approval set at = now() - interval '25 hours'")
    second = await seed_plan(cat_owner, moves=moves, tag="b")
    await _approve_all_items(cat_api, second)

    row = await _approve(cat_api, second)

    assert abs(await _offset(cat_owner, row["apply_after"])) < timedelta(minutes=1)


async def test_given_the_approvals_of_another_mailbox_when_a_plan_is_approved_then_they_do_not_count(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, "mb1", threshold=10, delay_minutes=15)
    await set_apply_config(cat_owner, "mb2", threshold=10, delay_minutes=15)
    other = await seed_plan(cat_owner, "mb2", moves=((NIL, CAT_A),) * 9, tag="o")
    await _approve_all_items(cat_api, other)
    await _approve(cat_api, other)
    plan = await seed_plan(cat_owner, "mb1", moves=((NIL, CAT_A),) * 9, tag="p")
    await _approve_all_items(cat_api, plan)

    row = await _approve(cat_api, plan)

    assert abs(await _offset(cat_owner, row["apply_after"])) < timedelta(minutes=1)


async def test_given_an_approval_when_it_is_recorded_then_the_approval_row_counts_the_approved_items_with_the_actor(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner)
    plan = await seed_plan(cat_owner)
    await cat_api.fetchval(DECIDE, plan.mailbox, plan.plan_id, 5, scope_ids(plan.item_ids[:2]), "approved")

    await _approve(cat_api, plan)

    rows = await cat_owner.fetch("select * from categories.plan_approval")
    assert len(rows) == 1
    assert (rows[0]["plan_id"], rows[0]["approved_count"], rows[0]["channel"]) == (plan.plan_id, 2, "web")
    assert rows[0]["actor_digest"] == hashlib.sha256(API_ROLE.encode()).hexdigest()


async def test_given_pending_items_at_approval_when_the_plan_is_approved_then_they_are_rejected_and_enter_rejection(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner)
    plan = await seed_plan(cat_owner, list_version=3)
    await cat_api.fetchval(DECIDE, plan.mailbox, plan.plan_id, 5, scope_ids(plan.item_ids[:2]), "approved")
    await cat_api.fetchval(DECIDE, plan.mailbox, plan.plan_id, 5, scope_ids([plan.item_ids[2]]), "rejected")

    await _approve(cat_api, plan)

    items = await cat_owner.fetch(
        "select decision, state from categories.plan_item where plan_id = $1 order by id", plan.plan_id
    )
    assert [(r["decision"], r["state"]) for r in items] == [("approved", "approved")] * 2 + [
        ("rejected", "rejected")
    ] * 3
    rejected = await cat_owner.fetch("select message_id, list_version from categories.rejection order by message_id")
    assert [(r["message_id"], r["list_version"]) for r in rejected] == [(m, 3) for m in plan.message_ids[2:]]


async def test_given_a_repeated_approval_when_the_plan_is_already_scheduled_then_the_current_state_comes_back(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=1, delay_minutes=15)
    plan = await seed_plan(cat_owner)
    await _approve_all_items(cat_api, plan)
    first = await _approve(cat_api, plan)

    second = await _approve(cat_api, plan)

    assert (second["state"], second["apply_after"]) == (first["state"], first["apply_after"])
    assert await cat_owner.fetchval("select count(*) from categories.plan_approval") == 1


async def test_given_a_plan_that_has_moved_on_when_it_is_approved_again_then_409(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner)
    plan = await seed_plan(cat_owner, state="applying")

    with pytest.raises(asyncpg.PostgresError) as error:
        await _approve(cat_api, plan)

    assert sqlstate_of(error.value) == "MC409"


@pytest.mark.parametrize("state", ["building", "cancelled", "replaced", "discarded"])
async def test_given_a_plan_that_is_not_ready_when_it_is_approved_then_409_and_nothing_changes(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, state: str
) -> None:
    await set_apply_config(cat_owner)
    plan = await seed_plan(cat_owner, state=state)

    with pytest.raises(asyncpg.PostgresError) as error:
        await _approve(cat_api, plan)

    assert sqlstate_of(error.value) == "MC409"
    assert await cat_owner.fetchval("select count(*) from categories.plan_approval") == 0
    assert await cat_owner.fetchval("select count(*) from categories.rejection") == 0


async def test_given_a_wrong_count_or_the_wrong_mailbox_when_a_plan_is_approved_then_409_and_nothing_changes(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner)
    plan = await seed_plan(cat_owner)

    for mailbox, count in (("mb1", 4), ("mb1", 6), ("mb2", 5)):
        with pytest.raises(asyncpg.PostgresError) as error:
            await cat_api.fetchrow(APPROVE, mailbox, plan.plan_id, count)
        assert sqlstate_of(error.value) == "MC409"

    assert await cat_owner.fetchval("select state from categories.plan where id = $1", plan.plan_id) == "ready"
    assert await cat_owner.fetchval("select count(*) from categories.plan_approval") == 0
    assert await cat_owner.fetchval("select count(*) from categories.rejection") == 0


async def test_given_no_apply_config_when_a_plan_is_approved_then_it_is_refused_instead_of_applied_unchecked(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, moves=((CAT_A, CAT_B),))

    with pytest.raises(asyncpg.PostgresError) as error:
        await _approve(cat_api, plan)

    assert sqlstate_of(error.value) == "MC409"
    assert await cat_owner.fetchval("select state from categories.plan where id = $1", plan.plan_id) == "ready"
