"""U-mail-categories-12, criteria 2 and 3 (AC-13, AC-27, AC-32, AC-36): ``categories.record_decision``."""

from __future__ import annotations

import hashlib
import json
import uuid

import asyncpg
import pytest

from tests.db.conftest import API_ROLE
from tests.db.plan_support import (
    CAT_A,
    NIL,
    SeededPlan,
    error_text,
    scope_all,
    scope_group,
    scope_ids,
    seed_plan,
    sqlstate_of,
)

CALL = "select categories.record_decision($1, $2, $3, $4::jsonb, $5)"


async def _decide(
    connection: asyncpg.Connection, plan: SeededPlan, count: int, scope: str, decision: str = "approved"
) -> int:
    return int(str(await connection.fetchval(CALL, plan.mailbox, plan.plan_id, count, scope, decision)))


async def _items(owner: asyncpg.Connection, plan: SeededPlan) -> list[tuple[str, str]]:
    rows = await owner.fetch(
        "select decision, state from categories.plan_item where plan_id = $1 order by id", plan.plan_id
    )
    return [(r["decision"], r["state"]) for r in rows]


async def _decision_rows(owner: asyncpg.Connection) -> list[asyncpg.Record]:
    return await owner.fetch("select * from categories.plan_decision order by id")


async def test_given_a_ready_plan_when_all_is_approved_with_the_right_count_then_decisions_and_an_audit_row_are_set(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    changed = await _decide(cat_api, plan, 5, scope_all())

    assert changed == 5
    assert await _items(cat_owner, plan) == [("approved", "approved")] * 5
    rows = await _decision_rows(cat_owner)
    assert len(rows) == 1
    assert (rows[0]["plan_id"], rows[0]["scope"], rows[0]["item_count"], rows[0]["decision"], rows[0]["channel"]) == (
        plan.plan_id,
        "all",
        5,
        "approved",
        "web",
    )
    assert rows[0]["actor_digest"] == hashlib.sha256(API_ROLE.encode()).hexdigest()


async def test_given_a_group_when_it_is_rejected_then_only_its_items_change(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)  # two items move Other -> A

    changed = await _decide(cat_api, plan, 5, scope_group(NIL, CAT_A, 2), "rejected")

    assert changed == 2
    assert await _items(cat_owner, plan) == [("rejected", "rejected")] * 2 + [("pending", "pending")] * 3
    assert (await _decision_rows(cat_owner))[0]["scope"] == "group"


async def test_given_chosen_ids_when_they_are_approved_then_only_those_items_change_and_the_decision_can_flip(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    await _decide(cat_api, plan, 5, scope_ids([plan.item_ids[0], plan.item_ids[4]]))
    await _decide(cat_api, plan, 5, scope_ids([plan.item_ids[4]]), "rejected")

    assert await _items(cat_owner, plan) == [
        ("approved", "approved"),
        ("pending", "pending"),
        ("pending", "pending"),
        ("pending", "pending"),
        ("rejected", "rejected"),
    ]
    assert [r["scope"] for r in await _decision_rows(cat_owner)] == ["ids", "ids"]


async def test_given_the_same_decision_twice_when_it_is_repeated_then_it_succeeds_and_both_calls_are_audited(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    await _decide(cat_api, plan, 5, scope_all())
    await _decide(cat_api, plan, 5, scope_all())

    assert await _items(cat_owner, plan) == [("approved", "approved")] * 5
    assert len(await _decision_rows(cat_owner)) == 2


async def test_given_a_decision_when_the_plan_is_read_then_its_last_activity_moves(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)
    await cat_owner.execute(
        "update categories.plan set last_activity_at = now() - interval '3 days' where id = $1", plan.plan_id
    )

    await _decide(cat_api, plan, 5, scope_all())

    assert await cat_owner.fetchval(
        "select last_activity_at > now() - interval '1 minute' from categories.plan where id = $1", plan.plan_id
    )


async def _expect_409(
    cat_api: asyncpg.Connection, mailbox: str, plan_id: uuid.UUID, count: int, scope: str
) -> asyncpg.PostgresError:
    with pytest.raises(asyncpg.PostgresError) as error:
        await cat_api.fetchval(CALL, mailbox, plan_id, count, scope, "approved")
    assert sqlstate_of(error.value) == "MC409", error.value
    return error.value


async def _assert_nothing_changed(owner: asyncpg.Connection, plan: SeededPlan, expected_items: int) -> None:
    assert await _items(owner, plan) == [("pending", "pending")] * expected_items
    assert await _decision_rows(owner) == []


async def test_given_a_wrong_item_count_when_a_decision_is_made_then_409_and_nothing_changes(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    for count in (4, 6, 0):
        await _expect_409(cat_api, plan.mailbox, plan.plan_id, count, scope_all())

    await _assert_nothing_changed(cat_owner, plan, 5)


async def test_given_a_group_count_that_no_longer_matches_when_a_decision_is_made_then_409(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    await _expect_409(cat_api, plan.mailbox, plan.plan_id, 5, scope_group(NIL, CAT_A, 3))

    await _assert_nothing_changed(cat_owner, plan, 5)


async def test_given_ids_of_another_plan_or_mailbox_when_a_decision_is_made_then_409_and_nothing_changes(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)
    old_plan = await seed_plan(cat_owner, state="applied", tag="old")  # another plan of the same mailbox
    foreign = await seed_plan(cat_owner, "mb2", tag="x")  # a plan of another mailbox

    for stranger in (old_plan.item_ids[0], foreign.item_ids[0], 9_999_999):
        await _expect_409(cat_api, plan.mailbox, plan.plan_id, 5, scope_ids([plan.item_ids[0], stranger]))

    await _assert_nothing_changed(cat_owner, plan, 5)


async def test_given_more_than_200_ids_when_a_decision_is_made_then_409(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    await _expect_409(cat_api, plan.mailbox, plan.plan_id, 5, scope_ids(list(range(1, 202))))

    await _assert_nothing_changed(cat_owner, plan, 5)


@pytest.mark.parametrize("state", ["building", "scheduled", "applying", "applied", "cancelled", "replaced"])
async def test_given_a_plan_that_is_not_ready_when_a_decision_is_made_then_409(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, state: str
) -> None:
    plan = await seed_plan(cat_owner, state=state)

    await _expect_409(cat_api, plan.mailbox, plan.plan_id, 5, scope_all())

    await _assert_nothing_changed(cat_owner, plan, 5)


async def test_given_the_plan_of_another_mailbox_or_none_when_a_decision_is_made_then_409(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    await _expect_409(cat_api, "mb2", plan.plan_id, 5, scope_all())
    await _expect_409(cat_api, "mb1", uuid.uuid4(), 5, scope_all())

    await _assert_nothing_changed(cat_owner, plan, 5)


@pytest.mark.parametrize(
    "scope",
    [
        json.dumps({"kind": "everything"}),
        json.dumps({"kind": "ids", "ids": ["1; drop table categories.plan"]}),
        json.dumps({"kind": "ids", "ids": [1.5]}),
        json.dumps({"kind": "ids"}),
        json.dumps({"kind": "group", "from": "not-a-uuid", "to": str(CAT_A), "groupCount": 1}),
        json.dumps({"kind": "group", "from": str(NIL), "to": str(CAT_A)}),
        json.dumps(["all"]),
        "null",
    ],
)
async def test_given_a_malformed_scope_when_a_decision_is_made_then_it_is_refused_without_echoing_the_input(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, scope: str
) -> None:
    plan = await seed_plan(cat_owner)

    with pytest.raises(asyncpg.PostgresError) as error:
        await cat_api.fetchval(CALL, plan.mailbox, plan.plan_id, 5, scope, "approved")

    assert sqlstate_of(error.value) in {"22023", "MC409"}
    assert "drop table" not in str(error.value)
    await _assert_nothing_changed(cat_owner, plan, 5)


async def test_given_an_unknown_decision_when_a_decision_is_made_then_it_is_refused(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    with pytest.raises(asyncpg.PostgresError) as error:
        await cat_api.fetchval(CALL, plan.mailbox, plan.plan_id, 5, scope_all(), "maybe")

    assert sqlstate_of(error.value) == "22023"
    await _assert_nothing_changed(cat_owner, plan, 5)


async def test_given_a_refusal_when_its_message_is_read_then_it_carries_no_row_value(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)
    error = await _expect_409(cat_api, plan.mailbox, plan.plan_id, 4, scope_all())

    text = error_text(error)
    for secret in (str(plan.plan_id), "sender@example.test", "A subject", plan.message_ids[0], str(NIL)):
        assert secret not in text
