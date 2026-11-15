"""U-mail-categories-22, criteria 1 and 2 and open points (a) to (e) of the earlier reports: apply and move back on PostgreSQL.

Every test acts as the agent role. Two stores on two sessions stand for two agent processes. The owner seeds plans, as
``approve_plan`` and the api would leave them.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.core.resort_plan import ItemState, PlanState
from app.db.pg_resort import PgApplyStore, channel_of
from app.usecases.resort_apply import AuditMove, SkipReason
from tests.db.conftest import AGENT_ROLE, API_ROLE
from tests.db.plan_support import seed_plan
from tests.db.resort_support import MAILBOX, agent_sessions, seed_approval, seed_list

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]  # the fixture is used by name

AGENT_DIGEST = hashlib.sha256(AGENT_ROLE.encode()).hexdigest()
API_DIGEST = hashlib.sha256(API_ROLE.encode()).hexdigest()


async def _scheduled(owner: asyncpg.Connection, *, moves: int = 3, channel: str = "web", state: str = "scheduled") -> uuid.UUID:
    """A plan in ``state`` with ``moves`` approved items, an approval of ``channel`` and ``apply_after`` in the past."""
    if not await owner.fetchval("select count(*) from categories.list_version"):
        await seed_list(owner, ["Finance", "Travel"])
    old, new = uuid.UUID(int=0), uuid.UUID(int=1)
    plan = await seed_plan(owner, MAILBOX, state=state, moves=((old, new),) * moves)
    await owner.execute("update categories.plan_item set decision = 'approved', state = 'approved' where plan_id = $1", plan.plan_id)
    await owner.execute("update categories.plan set apply_after = now() - interval '1 minute' where id = $1", plan.plan_id)
    await seed_approval(owner, plan.plan_id, channel)
    return plan.plan_id


async def test_given_applied_and_cancelled_plans_when_listed_then_they_are_not_for_the_apply(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    await _scheduled(cat_owner, state="applied")
    await _scheduled(cat_owner, state="cancelled")

    assert await store.plans_to_apply() == []


async def test_given_an_approval_when_the_plan_is_listed_then_state_channel_and_digest_come_from_it(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, channel="telegram")

    [due] = await store.plans_to_apply()

    assert (due.plan_id, due.state, due.channel, due.actor_digest) == (plan_id, PlanState.SCHEDULED, "telegram", "c" * 64)
    assert due.apply_after is not None


async def test_given_two_agent_processes_when_both_claim_the_same_plan_then_exactly_one_wins(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    first, second = PgApplyStore(agent_sessions, MAILBOX), PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner)

    results = await asyncio.gather(first.claim(plan_id, "run-a"), second.claim(plan_id, "run-b"))

    assert sorted(results) == [False, True]
    assert await cat_owner.fetchval("select state from categories.plan") == "applying"
    winner = "run-a" if results[0] else "run-b"
    loser = "run-b" if results[0] else "run-a"
    assert await first.begin_batch(plan_id, winner)
    assert not await first.begin_batch(plan_id, loser)


async def test_given_a_run_that_crashed_when_its_lease_ended_then_another_run_takes_the_plan_over(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner)
    assert await store.claim(plan_id, "run-a")
    assert not await store.claim(plan_id, "run-b")  # the lease of run-a is alive

    await cat_owner.execute("update categories.plan set apply_lease_until = now() - interval '1 second'")

    assert await store.claim(plan_id, "run-b")
    assert not await store.begin_batch(plan_id, "run-a")  # the old run is no longer ours
    assert await store.begin_batch(plan_id, "run-b")
    assert not await store.finish_plan(plan_id, "run-a")


async def test_given_a_plan_when_it_is_cancelled_then_scheduled_and_applying_end_cancelled_and_no_run_goes_on(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    scheduled = await _scheduled(cat_owner)

    assert await store.cancel(scheduled)
    assert not await store.claim(scheduled, "run-a")
    assert not await store.cancel(scheduled)  # already cancelled

    applying = await _scheduled(cat_owner)
    assert await store.claim(applying, "run-a")
    assert await store.cancel(applying)
    assert not await store.begin_batch(applying, "run-a")
    assert await cat_owner.fetchval("select state from categories.plan where id = $1", applying) == "cancelled"


async def test_given_an_applied_plan_when_it_is_cancelled_then_nothing_changes(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, state="applied")

    assert not await store.cancel(plan_id)
    assert await cat_owner.fetchval("select state from categories.plan") == "applied"


async def test_given_approved_items_when_they_are_finished_then_each_once_and_only_approved_ones_are_offered(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, moves=3)
    items = await store.next_items(plan_id, 2)
    assert len(items) == 2
    first, second = items[0].message_id, items[1].message_id

    assert await store.finish_item(plan_id, first, ItemState.APPLIED, None)
    assert not await store.finish_item(plan_id, first, ItemState.SKIPPED, SkipReason.GONE)  # decided once
    assert await store.finish_item(plan_id, second, ItemState.SKIPPED, SkipReason.PINNED)

    assert [i.message_id for i in await store.next_items(plan_id, 10)] == ["m2"]
    assert await store.item_counts(plan_id) == {ItemState.APPLIED: 1, ItemState.SKIPPED: 1, ItemState.APPROVED: 1}
    assert await cat_owner.fetchval("select reason from categories.plan_item where message_id = $1", second) == "pinned"


async def test_given_an_intent_when_it_is_recorded_then_the_channel_is_the_approvals_and_it_exists_once(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, channel="telegram")
    move = AuditMove("m0", "Label_1", "Label_2")

    assert await store.intent_for(plan_id, "m0") is None
    await store.record_intent(plan_id, move)
    await store.record_intent(plan_id, AuditMove("m0", "Label_8", "Label_9"))  # a retry changes nothing

    assert await store.intent_for(plan_id, "m0") == move
    row = await cat_owner.fetchrow("select channel, actor_digest, kind from categories.apply_audit")
    assert (row["channel"], row["actor_digest"], row["kind"]) == ("telegram", AGENT_DIGEST, "apply")
    assert await cat_owner.fetchval("select count(*) from categories.apply_audit") == 1


async def test_given_a_plan_without_approval_when_an_intent_is_recorded_then_it_is_refused_and_nothing_is_written(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner)
    await cat_owner.execute("delete from categories.plan_approval")

    with pytest.raises(LookupError):
        await store.record_intent(plan_id, AuditMove("m0", "Label_1", "Label_2"))

    assert await cat_owner.fetchval("select count(*) from categories.apply_audit") == 0


async def test_given_a_move_back_when_the_audit_is_read_then_only_the_apply_rows_come_back_not_the_restores(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, state="applied")
    await store.record_intent(plan_id, AuditMove("m0", "Label_1", "Label_2"))
    await store.record_intent(plan_id, AuditMove("m1", "", "Label_2"))

    await store.record_restore(plan_id, AuditMove("m0", "Label_2", "Label_1"), "web")

    assert await store.audit_moves(plan_id) == [AuditMove("m0", "Label_1", "Label_2"), AuditMove("m1", "", "Label_2")]
    rows = await cat_owner.fetch("select message_id, kind, channel, actor_digest from categories.apply_audit order by id")
    assert [(r["message_id"], r["kind"], r["channel"]) for r in rows] == [
        ("m0", "apply", "web"),
        ("m1", "apply", "web"),
        ("m0", "restore", "web"),
    ]
    assert rows[2]["actor_digest"] == AGENT_DIGEST


async def test_given_a_failing_item_when_attempts_are_counted_then_the_count_rises_and_a_decided_item_is_not_counted(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, moves=1)

    assert [await store.count_attempt(plan_id, "m0") for _ in range(3)] == [1, 2, 3]
    assert await store.finish_item(plan_id, "m0", ItemState.FAILED, None)
    assert await store.count_attempt(plan_id, "m0") == 3  # a finished item is no longer counted
    assert await cat_owner.fetchval("select state from categories.plan_item") == "failed"


async def test_given_only_the_lease_holder_when_the_plan_is_finished_then_exactly_one_caller_wins(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    first, second = PgApplyStore(agent_sessions, MAILBOX), PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner)
    assert await first.claim(plan_id, "run-a")

    results = await asyncio.gather(first.finish_plan(plan_id, "run-a"), second.finish_plan(plan_id, "run-a"))

    assert sorted(results) == [False, True]
    assert await cat_owner.fetchval("select state from categories.plan") == "applied"
    assert await cat_owner.fetchval("select terminal_at is not null from categories.plan")


async def test_given_an_applied_plan_when_applied_items_are_removed_then_skipped_and_failed_ones_stay(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, moves=3)
    await store.finish_item(plan_id, "m0", ItemState.APPLIED, None)
    await store.finish_item(plan_id, "m1", ItemState.SKIPPED, SkipReason.GONE)
    await store.finish_item(plan_id, "m2", ItemState.FAILED, None)

    await store.remove_applied_items(plan_id)  # the plan is not applied yet: nothing goes
    assert await cat_owner.fetchval("select count(*) from categories.plan_item") == 3

    await cat_owner.execute("update categories.plan set state = 'applying'")
    await cat_owner.execute("update categories.plan set state = 'applied'")
    await store.remove_applied_items(plan_id)

    assert sorted(r["message_id"] for r in await cat_owner.fetch("select message_id from categories.plan_item")) == ["m1", "m2"]


async def test_given_two_list_versions_when_the_current_categories_are_read_then_they_are_the_latest(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    await seed_list(cat_owner, ["Old"], version=1)
    ids = await seed_list(cat_owner, ["Finance", "Travel"], version=2)

    assert await store.current_categories() == {ids[0]: "Finance", ids[1]: "Travel"}


# --- move back ---------------------------------------------------------------------------------------------------


async def test_given_the_digest_of_a_login_when_the_channel_is_derived_then_it_is_the_one_of_that_role() -> None:
    assert channel_of(API_DIGEST) == "web"
    assert channel_of(AGENT_DIGEST) == "telegram"
    assert channel_of(hashlib.sha256(b"postgres").hexdigest()) == "operator"
    assert channel_of("z" * 64) == "operator"


async def test_given_a_request_of_the_api_when_requests_are_listed_then_the_job_has_channel_web(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, state="applied")
    await cat_api.execute("insert into categories.move_back_request (mailbox_id, plan_id) values ($1, $2)", MAILBOX, plan_id)

    [job] = await store.pending_requests()

    assert (job.plan_id, job.plan_state, job.channel, job.actor_digest) == (plan_id, PlanState.APPLIED, "web", API_DIGEST)


async def test_given_a_request_of_the_operator_when_requests_are_listed_then_the_job_has_channel_operator(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, state="applied")
    await cat_owner.execute("insert into categories.move_back_request (mailbox_id, plan_id) values ($1, $2)", MAILBOX, plan_id)

    [job] = await store.pending_requests()

    assert job.channel == "operator"


async def test_given_two_agent_processes_when_both_claim_a_request_then_exactly_one_wins_and_one_finishes_it(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    first, second = PgApplyStore(agent_sessions, MAILBOX), PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, state="applied")
    await cat_api.execute("insert into categories.move_back_request (mailbox_id, plan_id) values ($1, $2)", MAILBOX, plan_id)

    claimed = await asyncio.gather(first.claim_request(plan_id, "run-a"), second.claim_request(plan_id, "run-b"))

    assert sorted(claimed) == [False, True]
    winner = "run-a" if claimed[0] else "run-b"
    loser = "run-b" if claimed[0] else "run-a"
    assert await first.renew_request(plan_id, winner)
    assert not await first.renew_request(plan_id, loser)
    finished = await asyncio.gather(first.finish_request(plan_id, winner), second.finish_request(plan_id, winner))
    assert sorted(finished) == [False, True]
    assert await first.pending_requests() == []
    assert not await first.claim_request(plan_id, "run-c")  # processed once


async def test_given_a_request_whose_lease_ended_when_it_is_claimed_then_the_new_run_takes_it_over(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _scheduled(cat_owner, state="applied")
    await cat_api.execute("insert into categories.move_back_request (mailbox_id, plan_id) values ($1, $2)", MAILBOX, plan_id)
    assert await store.claim_request(plan_id, "run-a")
    assert not await store.claim_request(plan_id, "run-b")

    await cat_owner.execute("update categories.move_back_request set lease_until = now() - interval '1 second'")

    assert await store.claim_request(plan_id, "run-b")
    assert not await store.finish_request(plan_id, "run-a")
