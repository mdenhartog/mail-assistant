"""U-mail-categories-22 with U-16's ports: ``ApprovalStore`` and ``MoveBackRequests`` on the real database.

As the agent role. Cancel is one compare-and-set against ``apply_after``; a scheduled plan is announced once; the agent
may ask for a move back (its login is the actor the database writes) only for an applied plan, once.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.db.pg_approval import PgApprovalStore, PgMoveBackRequests
from app.db.pg_resort import PgApplyStore
from app.usecases.approval_notice import CancelOutcome
from tests.db.conftest import AGENT_ROLE
from tests.db.resort_support import MAILBOX, agent_sessions
from tests.db.test_pg_resort_apply import scheduled_plan

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]

AGENT_DIGEST = hashlib.sha256(AGENT_ROLE.encode()).hexdigest()


async def _delayed(owner: asyncpg.Connection, minutes: int = 15) -> Any:
    """A scheduled plan whose apply starts in ``minutes`` (the approval is now: a delayed plan)."""
    plan_id = await scheduled_plan(owner, moves=4)
    await owner.execute("update categories.plan_approval set at = now()")
    await owner.execute("update categories.plan set apply_after = now() + make_interval(mins => $1)", minutes)
    return plan_id


async def test_given_a_delayed_plan_when_listed_then_it_is_unannounced_with_its_count_until_it_is_marked(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApprovalStore(agent_sessions, MAILBOX)
    plan_id = await _delayed(cat_owner)

    [plan] = await store.unannounced()
    assert (plan.plan_id, plan.mail_count) == (plan_id, 4)
    assert plan.apply_after > datetime.now(UTC)

    await store.mark_announced(plan_id)

    assert await store.unannounced() == []


async def test_given_a_plan_without_delay_when_listed_then_it_is_not_announced(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApprovalStore(agent_sessions, MAILBOX)
    await _delayed(cat_owner)
    await cat_owner.execute("update categories.plan set apply_after = (select at from categories.plan_approval)")

    assert await store.unannounced() == []


async def test_given_a_delayed_plan_when_cancelled_before_the_start_then_it_ends_cancelled_once(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApprovalStore(agent_sessions, MAILBOX)
    plan_id = await _delayed(cat_owner)

    outcomes = await asyncio.gather(store.cancel_before_start(plan_id), store.cancel_before_start(plan_id))

    assert sorted(o.value for o in outcomes) == ["cancelled", "not_scheduled"]
    assert await cat_owner.fetchval("select state from categories.plan") == "cancelled"


async def test_given_the_start_has_passed_when_cancelled_then_too_late_and_the_plan_stays_scheduled(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApprovalStore(agent_sessions, MAILBOX)
    plan_id = await _delayed(cat_owner, minutes=-1)  # the start was a minute ago by the database clock

    assert await store.cancel_before_start(plan_id) is CancelOutcome.TOO_LATE
    assert await cat_owner.fetchval("select state from categories.plan") == "scheduled"


async def test_given_an_applied_plan_when_cancelled_then_not_scheduled(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApprovalStore(agent_sessions, MAILBOX)
    plan_id = await scheduled_plan(cat_owner, state="applied")

    assert await store.cancel_before_start(plan_id) is CancelOutcome.NOT_SCHEDULED


async def test_given_scheduled_and_applying_plans_when_the_open_plans_are_cancelled_then_all_end_cancelled(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApprovalStore(agent_sessions, MAILBOX)
    await scheduled_plan(cat_owner, state="applying")

    assert await store.cancel_open_plans() == 1
    assert await store.cancel_open_plans() == 0
    assert await cat_owner.fetchval("select state from categories.plan") == "cancelled"


async def test_given_an_applied_plan_when_a_move_back_is_asked_then_once_with_the_agent_as_actor(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    requests = PgMoveBackRequests(agent_sessions, MAILBOX)
    plan_id = await scheduled_plan(cat_owner, state="applied")

    assert await requests.request(plan_id)
    assert not await requests.request(plan_id)  # asked already

    row = await cat_owner.fetchrow("select processed, actor_digest from categories.move_back_request")
    assert row is not None
    assert (row["processed"], row["actor_digest"]) == (False, AGENT_DIGEST)


async def test_given_a_plan_that_is_not_applied_when_a_move_back_is_asked_then_it_is_refused(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    requests = PgMoveBackRequests(agent_sessions, MAILBOX)
    plan_id = await scheduled_plan(cat_owner)

    assert not await requests.request(plan_id)
    assert await cat_owner.fetchval("select count(*) from categories.move_back_request") == 0


async def test_given_the_deployment_numbers_when_they_are_written_then_the_row_is_replaced_and_the_mailbox_made(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApprovalStore(agent_sessions, "fresh")  # a mailbox that no list sync has made yet

    await store.write_config(threshold=50, delay_minutes=15)
    await store.write_config(threshold=9, delay_minutes=0)

    row = await cat_owner.fetchrow(
        "select threshold, delay_minutes from categories.apply_config where mailbox_id = 'fresh'"
    )
    assert row is not None
    assert (row["threshold"], row["delay_minutes"]) == (9, 0)


async def test_given_a_delayed_plan_that_was_never_announced_when_it_is_due_then_the_claim_fails_closed(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    approvals = PgApprovalStore(agent_sessions, MAILBOX)
    applies = PgApplyStore(agent_sessions, MAILBOX)
    plan_id = await _delayed(cat_owner)
    # the delay of 15 minutes has run out, but no notice was ever sent: nobody could have cancelled
    await cat_owner.execute("update categories.plan_approval set at = now() - interval '30 minutes'")
    await cat_owner.execute("update categories.plan set apply_after = now() - interval '1 second'")

    assert not await applies.claim(plan_id, "run-a")
    assert await cat_owner.fetchval("select state from categories.plan") == "scheduled"

    await approvals.mark_announced(plan_id)

    assert await applies.claim(plan_id, "run-a")


async def test_given_a_plan_without_delay_when_it_is_claimed_then_no_notice_is_needed(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan_id = await scheduled_plan(cat_owner)  # apply_after is not after the approval: nothing to announce

    assert await PgApplyStore(agent_sessions, MAILBOX).claim(plan_id, "run-a")


async def test_given_a_start_one_minute_away_when_cancelled_then_the_database_clock_decides(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    store = PgApprovalStore(agent_sessions, MAILBOX)
    plan_id = await _delayed(cat_owner, minutes=1)  # the start is one minute away by the database clock

    outcome = await store.cancel_before_start(plan_id)

    assert outcome is CancelOutcome.CANCELLED
