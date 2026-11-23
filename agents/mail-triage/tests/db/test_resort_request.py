"""U-label-structure-20: revision 0029, the sort-again request, the plan columns and the system approval (ADR-0056).

Criteria 1 to 5 run on the migrated template database with the real roles (``SET SESSION AUTHORIZATION``), criterion 6
walks the revision up, down and up again.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic import command

from tests.db.conftest import API_ROLE, alembic_config, plain_url
from tests.db.plan_support import CAT_A, NIL, error_text, set_apply_config, sqlstate_of

if TYPE_CHECKING:
    from collections.abc import Sequence

REQUEST = "select categories.request_resort($1, $2::numeric)"
APPROVE = "select state, apply_after from categories.approve_system_plan($1)"
NEW_FUNCTIONS = ("categories.request_resort(text,numeric)", "categories.approve_system_plan(uuid)")  # regprocedure text


async def _request(owner: asyncpg.Connection, threshold: int, mailbox: str = "mb1") -> uuid.UUID:
    """A request row the owner writes (the trigger derives actor, channel and time)."""
    request_id = uuid.uuid4()
    await owner.execute(
        "insert into categories.resort_request (mailbox_id, id, threshold) values ($1, $2, $3)",
        mailbox,
        request_id,
        threshold,
    )
    return request_id


async def _plan(  # noqa: PLR0913
    owner: asyncpg.Connection,
    request_id: uuid.UUID | None,
    confidences: Sequence[int | None] = (),
    *,
    kind: str = "auto",
    state: str = "ready",
    mailbox: str = "mb1",
) -> uuid.UUID:
    """A plan of ``kind`` with one item per confidence; the threshold is copied from the request by the database."""
    plan_id = uuid.uuid4()
    await owner.execute(
        "insert into categories.plan (mailbox_id, id, list_version, state, kind, request_id) "
        "values ($1, $2, 1, $3, $4, $5)",
        mailbox,
        plan_id,
        state,
        kind,
        request_id,
    )
    for index, confidence in enumerate(confidences):
        await owner.execute(
            "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
            "old_category_id, new_category_id, confidence_pct) "
            "values ($1, $2, $3, 'Sender', 'sender@example.test', 'A subject', $4, $5, $6)",
            mailbox,
            plan_id,
            f"m{index}",
            NIL,
            CAT_A,
            confidence,
        )
    return plan_id


async def _offset(owner: asyncpg.Connection, moment: object) -> timedelta:
    """How far ``moment`` is from the database's now."""
    value = await owner.fetchval("select $1::timestamptz - now()", moment)
    assert isinstance(value, timedelta)
    return value


async def _count(owner: asyncpg.Connection, table: str, mailbox: str = "mb1") -> int:
    return int(str(await owner.fetchval(f"select count(*) from categories.{table} where mailbox_id = $1", mailbox)))  # noqa: S608


# --- 1: a threshold from 50 to 100 ------------------------------------------------------------------------------------
@pytest.mark.parametrize("threshold", [50, 75, 100])
async def test_given_a_threshold_from_50_to_100_when_the_api_requests_a_resort_then_one_request_row_exists(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, threshold: int
) -> None:
    request_id = await cat_api.fetchval(REQUEST, "mb1", Decimal(threshold))

    rows = await cat_owner.fetch("select * from categories.resort_request")
    assert len(rows) == 1
    row = rows[0]
    assert (row["id"], row["mailbox_id"], row["threshold"], row["channel"]) == (request_id, "mb1", threshold, "web")
    assert row["actor_digest"] == hashlib.sha256(API_ROLE.encode()).hexdigest()  # derived, never supplied
    assert row["at"] is not None


@pytest.mark.parametrize("threshold", [Decimal(49), Decimal(101), Decimal("50.5"), Decimal("99.9"), Decimal(0), None])
async def test_given_a_threshold_outside_the_range_or_not_whole_when_requested_then_it_is_refused(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, threshold: Decimal | None
) -> None:
    with pytest.raises(asyncpg.PostgresError) as refused:
        await cat_api.fetchval(REQUEST, "mb1", threshold)

    assert sqlstate_of(refused.value) == "22023"
    assert await _count(cat_owner, "resort_request") == 0


async def test_given_a_request_row_when_the_table_checks_it_then_a_threshold_outside_the_range_is_refused(
    cat_owner: asyncpg.Connection,
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match="ck_resort_request_threshold"):
        await _request(cat_owner, 49)


async def test_given_a_request_when_the_caller_names_actor_channel_or_time_then_the_database_overrides_them(
    cat_owner: asyncpg.Connection,
) -> None:
    await cat_owner.execute(
        "insert into categories.resort_request (mailbox_id, threshold, channel, actor_digest, at) "
        "values ('mb1', 60, 'telegram', $1, '2001-01-01')",
        "f" * 64,
    )

    row = await cat_owner.fetchrow("select channel, actor_digest, at from categories.resort_request")
    assert row is not None
    assert row["channel"] == "operator"  # the owner's session is not a runtime role
    assert row["actor_digest"] != "f" * 64
    assert row["at"].year > 2001


# --- 2: one open plan per mailbox and kind ----------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["auto", "review"])
@pytest.mark.parametrize("state", ["building", "ready", "scheduled", "applying"])
async def test_given_an_open_plan_when_a_resort_is_requested_then_it_is_refused(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, kind: str, state: str
) -> None:
    await _plan(cat_owner, await _request(cat_owner, 70), (80,), kind=kind, state=state)
    before = await _count(cat_owner, "resort_request")

    with pytest.raises(asyncpg.PostgresError) as refused:
        await cat_api.fetchval(REQUEST, "mb1", Decimal(60))

    assert sqlstate_of(refused.value) == "MC409"
    assert await _count(cat_owner, "resort_request") == before


@pytest.mark.parametrize("state", ["applied", "replaced", "discarded", "cancelled"])
async def test_given_only_ended_plans_or_another_mailboxs_plan_when_a_resort_is_requested_then_it_is_accepted(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, state: str
) -> None:
    await _plan(cat_owner, None, kind="review", state=state)
    await _plan(cat_owner, await _request(cat_owner, 70, "mb2"), kind="auto", state="ready", mailbox="mb2")

    await cat_api.fetchval(REQUEST, "mb1", Decimal(60))

    assert await _count(cat_owner, "resort_request", "mb1") == 1
    assert await _count(cat_owner, "resort_request", "mb2") == 1


async def test_given_two_open_plans_of_one_kind_when_the_second_is_made_then_the_index_refuses_it_but_not_another_kind(
    cat_owner: asyncpg.Connection,
) -> None:
    request_id = await _request(cat_owner, 70)
    await _plan(cat_owner, request_id, kind="auto")
    await _plan(cat_owner, request_id, kind="review")  # the other kind is its own slot

    with pytest.raises(asyncpg.UniqueViolationError, match="uq_plan_one_open"):
        await _plan(cat_owner, request_id, kind="auto")


async def test_given_a_plan_kind_when_it_is_unknown_or_without_a_request_then_a_check_refuses_it(
    cat_owner: asyncpg.Connection,
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match="ck_plan_kind"):
        await _plan(cat_owner, None, kind="other")
    with pytest.raises(asyncpg.CheckViolationError, match="ck_plan_request"):
        await _plan(cat_owner, None, kind="auto")  # a sort-again plan always has its request


# --- 3: the api role has no way around the functions ------------------------------------------------------------------
async def test_given_the_api_role_when_it_calls_the_system_approval_then_postgres_refuses_with_42501(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan_id = await _plan(cat_owner, await _request(cat_owner, 70), (90,))

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await cat_api.fetch(APPROVE, plan_id)

    assert await cat_owner.fetchval("select state from categories.plan where id = $1", plan_id) == "ready"


@pytest.mark.parametrize(
    "statement",
    [
        "insert into categories.plan_approval (mailbox_id, plan_id, approved_count, channel, actor_digest) "
        "values ('mb1', gen_random_uuid(), 1, 'web', repeat('a', 64))",
        "insert into categories.plan_decision "
        "(mailbox_id, plan_id, scope, item_count, decision, channel, actor_digest) "
        "values ('mb1', gen_random_uuid(), 'all', 1, 'approved', 'web', repeat('a', 64))",
        "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
        "old_category_id, new_category_id) values ('mb1', gen_random_uuid(), 'x', 'n', 'a', 's', gen_random_uuid(), "
        "gen_random_uuid())",
        "update categories.plan_item set decision_source = 'threshold'",
        "update categories.plan_item set confidence_pct = 100",
        "update categories.plan_item set decision = 'approved'",
        "update categories.plan set threshold = 50",
        "update categories.plan set state = 'scheduled'",
        "insert into categories.resort_request (mailbox_id, threshold) values ('mb1', 50)",
        "update categories.resort_request set threshold = 50",
        "delete from categories.resort_request",
    ],
)
async def test_given_the_api_role_when_it_writes_an_approval_decision_item_or_request_directly_then_42501(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, statement: str
) -> None:
    await _plan(cat_owner, await _request(cat_owner, 70), (90,))

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await cat_api.execute(statement)


async def test_given_the_agent_role_when_it_calls_request_resort_then_postgres_refuses_with_42501(
    cat_agent: asyncpg.Connection,
) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await cat_agent.fetchval(REQUEST, "mb1", Decimal(60))


async def test_given_the_api_role_when_it_reads_the_requests_and_the_new_item_columns_then_it_may(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await _plan(cat_owner, await _request(cat_owner, 70), (90,))

    assert await cat_api.fetchval("select count(*) from categories.resort_request") == 1
    row = await cat_api.fetchrow(
        "select confidence_pct, decision_source, tip, old_topic_id, new_topic_id from categories.plan_item"
    )
    assert row is not None
    assert (row["confidence_pct"], row["decision_source"]) == (90, "user")
    assert await cat_api.fetchrow("select kind, threshold from categories.plan") is not None


# --- 4: the system approval re-checks every item ----------------------------------------------------------------------
async def test_given_an_auto_plan_with_an_item_below_the_threshold_when_the_agent_approves_then_it_is_refused(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner)
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), (95, 79, 100))

    with pytest.raises(asyncpg.PostgresError) as refused:
        await cat_agent.fetch(APPROVE, plan_id)

    assert sqlstate_of(refused.value) == "MC409"
    assert "below" in error_text(refused.value)
    assert await cat_owner.fetchval("select state from categories.plan where id = $1", plan_id) == "ready"
    assert await _count(cat_owner, "plan_approval") == 0
    assert await cat_owner.fetchval("select count(*) from categories.plan_item where decision <> 'pending'") == 0


async def test_given_an_item_without_a_confidence_when_the_agent_approves_then_it_is_refused(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner)
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), (95, None))

    with pytest.raises(asyncpg.PostgresError) as refused:
        await cat_agent.fetch(APPROVE, plan_id)

    assert sqlstate_of(refused.value) == "MC409"


@pytest.mark.parametrize(("kind", "state"), [("review", "ready"), ("auto", "building"), ("auto", "applying")])
async def test_given_a_plan_that_is_not_a_ready_auto_plan_when_the_agent_approves_then_it_is_refused(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, kind: str, state: str
) -> None:
    await set_apply_config(cat_owner)
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), (95,), kind=kind, state=state)

    with pytest.raises(asyncpg.PostgresError) as refused:
        await cat_agent.fetch(APPROVE, plan_id)

    assert sqlstate_of(refused.value) == "MC409"


async def test_given_an_unknown_plan_when_the_agent_approves_then_it_is_refused(cat_agent: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.PostgresError) as refused:
        await cat_agent.fetch(APPROVE, uuid.uuid4())

    assert sqlstate_of(refused.value) == "MC409"


async def test_given_qualifying_items_when_the_agent_approves_then_the_plan_is_scheduled_with_source_threshold(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=50, delay_minutes=15)
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), (80, 95, 100))

    row = (await cat_agent.fetch(APPROVE, plan_id))[0]

    assert row["state"] == "scheduled"
    assert timedelta(minutes=14) < await _offset(cat_owner, row["apply_after"]) <= timedelta(minutes=15)
    plan = await cat_owner.fetchrow("select state, apply_after from categories.plan where id = $1", plan_id)
    assert plan is not None
    assert (plan["state"], plan["apply_after"]) == (row["state"], row["apply_after"])
    items = await cat_owner.fetch("select decision, state, decision_source, decided_at from categories.plan_item")
    assert {(i["decision"], i["state"], i["decision_source"]) for i in items} == {("approved", "approved", "threshold")}
    assert all(i["decided_at"] is not None for i in items)
    approval = await cat_owner.fetchrow("select * from categories.plan_approval")
    assert approval is not None
    assert (approval["plan_id"], approval["approved_count"], approval["mailbox_id"]) == (plan_id, 3, "mb1")
    assert approval["actor_digest"] == hashlib.sha256(b"mail_triage_runtime").hexdigest()


async def test_given_a_system_approval_when_the_24_hour_total_passes_the_limit_then_the_apply_waits_the_delay(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=4, delay_minutes=15)
    await cat_owner.execute(  # a user approval of 3 mails an hour ago counts toward the same 24 hours
        "insert into categories.plan_approval (mailbox_id, plan_id, approved_count, channel, actor_digest, at) "
        "values ('mb1', gen_random_uuid(), 3, 'web', repeat('c', 64), now() - interval '1 hour')"
    )
    plan_id = await _plan(cat_owner, await _request(cat_owner, 60), (70, 90))  # 3 + 2 = 5 > 4

    row = (await cat_agent.fetch(APPROVE, plan_id))[0]

    offset = await _offset(cat_owner, row["apply_after"])
    assert timedelta(minutes=14) < offset <= timedelta(minutes=15)


async def test_given_a_system_approval_when_the_next_user_approval_counts_then_the_system_items_are_in_the_total(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=4, delay_minutes=15)
    request_id = await _request(cat_owner, 60)
    auto = await _plan(cat_owner, request_id, (70, 90, 95))
    await cat_agent.fetch(APPROVE, auto)
    review = await _plan(cat_owner, request_id, (10, 20), kind="review")  # two more, user approved: 3 + 2 > 4
    await cat_api.fetchval(
        "select categories.record_decision('mb1', $1, 2, '{\"kind\": \"all\"}'::jsonb, 'approved')", review
    )

    row = (await cat_api.fetch("select state, apply_after from categories.approve_plan('mb1', $1, 2)", review))[0]

    assert timedelta(minutes=14) < await _offset(cat_owner, row["apply_after"])
    assert await cat_owner.fetchval("select decision_source from categories.plan_item where plan_id = $1", review) == (
        "user"
    )


async def test_given_a_scheduled_auto_plan_when_the_agent_approves_again_then_nothing_is_added(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner)
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), (90,))
    first = (await cat_agent.fetch(APPROVE, plan_id))[0]

    second = (await cat_agent.fetch(APPROVE, plan_id))[0]

    assert (second["state"], second["apply_after"]) == (first["state"], first["apply_after"])
    assert await _count(cat_owner, "plan_approval") == 1


async def test_given_an_agent_without_apply_settings_when_it_approves_then_it_is_refused_and_nothing_changes(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), (90,))

    with pytest.raises(asyncpg.PostgresError) as refused:
        await cat_agent.fetch(APPROVE, plan_id)

    assert sqlstate_of(refused.value) == "MC409"
    assert await cat_owner.fetchval("select state from categories.plan where id = $1", plan_id) == "ready"


async def test_given_the_agent_role_when_it_schedules_or_sets_a_source_itself_then_postgres_refuses_it(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _plan(cat_owner, await _request(cat_owner, 80), (90,))

    for statement in (
        "update categories.plan set state = 'scheduled'",
        "update categories.plan set threshold = 50",
        "update categories.plan set kind = 'review'",
        "update categories.plan_item set decision_source = 'threshold'",
        "update categories.plan_item set confidence_pct = 100",
        "update categories.plan_item set decision = 'approved', state = 'approved'",
        "insert into categories.plan_approval (mailbox_id, plan_id, approved_count, channel, actor_digest) "
        "values ('mb1', gen_random_uuid(), 1, 'telegram', repeat('a', 64))",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await cat_agent.execute(statement)


# --- 5: the plan keeps its copied threshold ---------------------------------------------------------------------------
async def test_given_a_running_plan_when_a_later_request_has_another_threshold_then_the_plan_keeps_its_own(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner)
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), (85, 90))
    with pytest.raises(asyncpg.PostgresError):  # the api's later request is refused while the plan runs
        await cat_api.fetchval(REQUEST, "mb1", Decimal(50))
    await _request(cat_owner, 50)  # even a later request row that exists changes nothing in the plan

    assert await cat_owner.fetchval("select threshold from categories.plan where id = $1", plan_id) == 80
    await cat_owner.execute("update categories.plan_item set confidence_pct = 70 where message_id = 'm0'")
    with pytest.raises(asyncpg.PostgresError) as refused:  # 70 passes the later 50 but not the stored 80
        await cat_agent.fetch(APPROVE, plan_id)
    assert sqlstate_of(refused.value) == "MC409"
    assert await cat_owner.fetchval("select threshold from categories.plan where id = $1", plan_id) == 80


@pytest.mark.parametrize("column", ["threshold", "kind", "request_id"])
async def test_given_a_plan_when_anyone_changes_its_kind_request_or_threshold_then_the_database_refuses_it(
    cat_owner: asyncpg.Connection, column: str
) -> None:
    request_id = await _request(cat_owner, 80)
    plan_id = await _plan(cat_owner, request_id, (90,))
    other = await _request(cat_owner, 50)
    values = {"threshold": "50", "kind": "'review'", "request_id": f"'{other}'"}

    with pytest.raises(asyncpg.PostgresError) as refused:
        await cat_owner.execute(f"update categories.plan set {column} = {values[column]} where id = $1", plan_id)  # noqa: S608

    assert sqlstate_of(refused.value) == "MC409"


async def test_given_the_agent_when_it_inserts_a_plan_with_a_request_then_the_threshold_is_copied_from_the_request(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    request_id = await _request(cat_owner, 65)
    other_mailbox = await _request(cat_owner, 90, "mb2")

    await cat_agent.execute(
        "insert into categories.plan (mailbox_id, list_version, kind, request_id) values ('mb1', 1, 'auto', $1)",
        request_id,
    )

    row = await cat_owner.fetchrow("select kind, threshold, state from categories.plan")
    assert row is not None
    assert (row["kind"], row["threshold"], row["state"]) == ("auto", 65, "building")
    with pytest.raises(asyncpg.PostgresError) as refused:  # a request of another mailbox is not this mailbox's
        await cat_agent.execute(
            "insert into categories.plan (mailbox_id, list_version, kind, request_id) values ('mb1', 1, 'review', $1)",
            other_mailbox,
        )
    assert sqlstate_of(refused.value) == "MC409"


async def test_given_the_agent_when_it_inserts_a_plan_without_kind_then_it_is_a_review_plan_without_threshold(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await cat_agent.execute("insert into categories.plan (mailbox_id, list_version) values ('mb1', 1)")

    row = await cat_owner.fetchrow("select kind, threshold, request_id from categories.plan")
    assert row is not None
    assert (row["kind"], row["threshold"], row["request_id"]) == ("review", None, None)


# --- the plan item columns --------------------------------------------------------------------------------------------
async def test_given_the_agent_when_it_writes_the_pair_confidence_and_tip_then_they_are_stored(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), kind="review")
    old_topic, old_extra, new_topic, new_extra = (uuid.uuid4() for _ in range(4))

    await cat_agent.execute(
        "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
        "old_category_id, new_category_id, old_topic_id, old_extra_id, new_topic_id, new_extra_id, confidence_pct) "
        "values ('mb1', $1, 'm', 's', 'a@example.test', 'x', $2, $3, $4, $5, $6, $7, 42)",
        plan_id,
        NIL,
        CAT_A,
        old_topic,
        old_extra,
        new_topic,
        new_extra,
    )
    await cat_agent.execute("update categories.plan_item set tip = 'Add a sender rule for example.test'")

    row = await cat_owner.fetchrow("select * from categories.plan_item")
    assert row is not None
    assert (row["old_topic_id"], row["old_extra_id"], row["new_topic_id"], row["new_extra_id"]) == (
        old_topic,
        old_extra,
        new_topic,
        new_extra,
    )
    assert (row["confidence_pct"], row["decision_source"], row["tip"]) == (
        42,
        "user",
        "Add a sender rule for example.test",
    )


@pytest.mark.parametrize(
    ("assignment", "constraint"),
    [
        ("confidence_pct = 101", "ck_plan_item_confidence"),
        ("confidence_pct = -1", "ck_plan_item_confidence"),
        ("decision_source = 'model'", "ck_plan_item_decision_source"),
        ("decision_source = 'threshold'", "ck_plan_item_threshold_approved"),  # still pending
        ("tip = repeat('x', 501)", "ck_plan_item_tip"),
    ],
)
async def test_given_a_plan_item_when_a_new_column_holds_a_bad_value_then_a_check_refuses_it(
    cat_owner: asyncpg.Connection, assignment: str, constraint: str
) -> None:
    await _plan(cat_owner, await _request(cat_owner, 80), (90,))

    with pytest.raises(asyncpg.CheckViolationError, match=constraint):
        await cat_owner.execute(f"update categories.plan_item set {assignment}")  # noqa: S608


# --- the retention of the requests ------------------------------------------------------------------------------------
async def test_given_old_requests_when_the_purge_runs_then_those_over_a_year_old_go(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _request(cat_owner, 70)
    await _request(cat_owner, 80)
    await cat_owner.execute("update categories.resort_request set at = now() - interval '2 years' where threshold = 70")

    removed = await cat_agent.fetchval("select categories.purge_expired()")

    assert '"resort_request": 1' in str(removed)
    assert await cat_owner.fetchval("select threshold from categories.resort_request") == 80


# --- 6: the migration is idempotent and reversible --------------------------------------------------------------------
async def _functions(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch(
        "select p.oid::regprocedure::text as name from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'categories' and p.proname in ('request_resort', 'approve_system_plan')"
    )
    return {r["name"] for r in rows}


async def _columns(connection: asyncpg.Connection, table: str) -> set[str]:
    rows = await connection.fetch(
        "select column_name from information_schema.columns where table_schema = 'categories' and table_name = $1",
        table,
    )
    return {r["column_name"] for r in rows}


async def test_given_a_ready_auto_plan_when_the_api_decides_or_approves_it_then_both_refuse_and_nothing_changes(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=1, delay_minutes=15)
    plan_id = await _plan(cat_owner, await _request(cat_owner, 80), (90, 95))  # an auto plan the owner made ready
    for call in (
        "select categories.record_decision('mb1', $1, 2, '{\"kind\": \"all\"}'::jsonb, 'approved')",
        "select * from categories.approve_plan('mb1', $1, 2)",
    ):
        with pytest.raises(asyncpg.PostgresError) as refused:
            await cat_api.fetch(call, plan_id)
        assert sqlstate_of(refused.value) == "MC409"

    plan = await cat_owner.fetchrow("select state, apply_after from categories.plan where id = $1", plan_id)
    assert plan is not None
    assert (plan["state"], plan["apply_after"]) == ("ready", None)
    assert await cat_owner.fetchval("select count(*) from categories.plan_item where decision <> 'pending'") == 0
    assert await _count(cat_owner, "plan_decision") == 0
    assert await _count(cat_owner, "plan_approval") == 0


async def test_given_0029_when_it_runs_twice_goes_down_and_up_again_then_it_is_idempotent_and_reversible(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0028")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await connection.execute("insert into categories.mailbox (id) values ('mb1')")
        old_plan = uuid.uuid4()
        await connection.execute(
            "insert into categories.plan (mailbox_id, id, list_version, state) values ('mb1', $1, 1, 'ready')", old_plan
        )
        await connection.execute(
            "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
            "old_category_id, new_category_id) values ('mb1', $1, 'm', 's', 'a', 'x', $2, $3)",
            old_plan,
            NIL,
            CAT_A,
        )
        assert await _functions(connection) == set()
        assert "kind" not in await _columns(connection, "plan")

        await asyncio.to_thread(command.upgrade, config, "0029")
        await asyncio.to_thread(command.upgrade, config, "head")  # a second run changes nothing

        assert await _functions(connection) == set(NEW_FUNCTIONS)
        assert {"kind", "request_id", "threshold"} <= await _columns(connection, "plan")
        assert {"old_topic_id", "confidence_pct", "decision_source", "tip"} <= await _columns(connection, "plan_item")
        old = await connection.fetchrow("select kind, threshold, request_id from categories.plan")
        assert old is not None
        assert (old["kind"], old["threshold"], old["request_id"]) == ("review", None, None)  # the old plan stays
        assert await connection.fetchval("select decision_source from categories.plan_item") == "user"
        for function in NEW_FUNCTIONS:  # owned by the non-login definer, search path pinned, not callable by PUBLIC
            row = await connection.fetchrow(
                "select pg_get_userbyid(p.proowner) as owner, p.prosecdef, p.proconfig, "
                "has_function_privilege('public', p.oid, 'EXECUTE') as public_exec "
                "from pg_proc p where p.oid = $1::regprocedure",
                function,
            )
            assert row is not None
            assert (row["owner"], row["prosecdef"], row["public_exec"]) == ("categories_definer", True, False)
            assert "search_path=pg_catalog, pg_temp" in row["proconfig"]

        await asyncio.to_thread(command.downgrade, config, "0028")

        assert await _functions(connection) == set()
        assert "resort_request" not in {
            r["tablename"]
            for r in await connection.fetch("select tablename from pg_tables where schemaname = 'categories'")
        }
        assert not {"kind", "request_id", "threshold"} & await _columns(connection, "plan")
        assert not {"confidence_pct", "decision_source", "tip"} & await _columns(connection, "plan_item")
        index = await connection.fetchval("select indexdef from pg_indexes where indexname = 'uq_plan_one_open'")
        assert "kind" not in index
        purge = await connection.fetchval("select pg_get_functiondef('categories.purge_expired()'::regprocedure)")
        assert "resort_request" not in purge
        for function in ("approve_plan(text,uuid,integer)", "record_decision(text,uuid,integer,jsonb,text)"):
            body = await connection.fetchval(f"select pg_get_functiondef('categories.{function}'::regprocedure)")
            assert "p.kind = 'review'" not in body  # the 0015 bodies are back
        checks = await connection.fetchval(
            "select string_agg(pg_get_constraintdef(oid), ' ') from pg_constraint "
            "where conname in ('ck_plan_approval_channel', 'ck_apply_audit_channel')"
        )
        assert "system" not in checks
        assert await connection.fetchval("select count(*) from categories.plan_item") == 1  # the old rows survive

        await asyncio.to_thread(command.upgrade, config, "0029")

        assert await _functions(connection) == set(NEW_FUNCTIONS)
        index = await connection.fetchval("select indexdef from pg_indexes where indexname = 'uq_plan_one_open'")
        assert "kind" in index
        checks = await connection.fetchval(
            "select string_agg(pg_get_constraintdef(oid), ' ') from pg_constraint "
            "where conname in ('ck_plan_approval_channel', 'ck_apply_audit_channel')"
        )
        assert checks.count("system") == 2
    finally:
        await connection.close()
