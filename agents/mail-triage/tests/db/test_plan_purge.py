"""U-mail-categories-12, criterion 8 (AC-19, AC-47): the retention of the plan tables in ``purge_expired()``."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tests.db.conftest import write_list
from tests.db.plan_support import seed_plan

if TYPE_CHECKING:
    import asyncpg

DIGEST = "a" * 64


async def _purge(connection: asyncpg.Connection) -> dict[str, int]:
    return json.loads(str(await connection.fetchval("select categories.purge_expired()")))


async def _count(owner: asyncpg.Connection, table: str, where: str = "true") -> int:
    return int(str(await owner.fetchval(f"select count(*) from categories.{table} where {where}")))


async def _age_plan(owner: asyncpg.Connection, plan_id: object, *, activity: str, terminal: str | None = None) -> None:
    """Backdate a plan: its last activity, and when it ended if ``terminal`` is given (an interval text)."""
    await owner.execute(
        "update categories.plan set last_activity_at = now() - $2::text::interval, "
        "terminal_at = case when $3::text is null then terminal_at else now() - $3::text::interval end "
        "where id = $1",
        plan_id,
        activity,
        terminal,
    )


async def test_given_an_applied_plan_when_the_purge_runs_then_its_items_go_at_once_and_the_plan_stays_14_days(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, state="applying")
    await cat_owner.execute("update categories.plan set state = 'applied' where id = $1", plan.plan_id)

    counts = await _purge(cat_agent)

    assert counts["plan_item"] == 5
    assert await _count(cat_owner, "plan_item") == 0
    assert await _count(cat_owner, "plan") == 1
    await _age_plan(cat_owner, plan.plan_id, activity="20 days", terminal="15 days")
    assert (await _purge(cat_agent))["plan"] == 1
    assert await _count(cat_owner, "plan") == 0


async def test_given_a_ready_plan_when_the_last_decision_is_14_days_old_then_its_items_go_and_a_younger_plan_keeps_them(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    old = await seed_plan(cat_owner, "mb1", state="ready", tag="o")
    young = await seed_plan(cat_owner, "mb2", state="ready", tag="y")
    await _age_plan(cat_owner, old.plan_id, activity="15 days")
    await _age_plan(cat_owner, young.plan_id, activity="13 days")

    await _purge(cat_agent)

    assert await _count(cat_owner, "plan_item", f"plan_id = '{old.plan_id}'") == 0
    assert await _count(cat_owner, "plan_item", f"plan_id = '{young.plan_id}'") == 5
    assert await _count(cat_owner, "plan") == 2  # a ready plan is discarded by the agent, not deleted by the purge


async def test_given_plans_that_ended_when_the_purge_runs_then_they_go_14_days_after_they_ended(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    for state, mailbox in (("cancelled", "mb1"), ("replaced", "mb2")):
        plan = await seed_plan(cat_owner, mailbox, state=state, tag=state[:2])
        terminal = "15 days" if state == "cancelled" else "13 days"
        await _age_plan(cat_owner, plan.plan_id, activity="1 day", terminal=terminal)

    await _purge(cat_agent)

    assert await _count(cat_owner, "plan", "state = 'cancelled'") == 0
    assert await _count(cat_owner, "plan", "state = 'replaced'") == 1
    assert await _count(cat_owner, "plan_item") == 5  # the items of the plan that ended 13 days ago stay


async def test_given_a_scheduled_or_applying_plan_when_it_is_old_then_the_purge_leaves_it_and_its_items(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    scheduled = await seed_plan(cat_owner, "mb1", state="scheduled", tag="s")
    await _age_plan(cat_owner, scheduled.plan_id, activity="40 days")

    await _purge(cat_agent)

    assert await _count(cat_owner, "plan") == 1
    assert await _count(cat_owner, "plan_item") == 5


async def test_given_audit_rows_when_the_purge_runs_then_those_over_a_year_go_and_younger_ones_stay(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, state="applied", moves=(), tag="a")
    for age in ("400 days", "300 days"):
        await cat_owner.execute(
            "insert into categories.plan_decision (mailbox_id, plan_id, scope, item_count, decision, channel, "
            "actor_digest, at) values ('mb1', $1, 'all', 1, 'approved', 'web', $2, now() - $3::text::interval)",
            plan.plan_id,
            DIGEST,
            age,
        )
        await cat_owner.execute(
            "insert into categories.plan_approval (mailbox_id, plan_id, approved_count, channel, actor_digest, at) "
            "values ('mb1', $1, 1, 'web', $2, now() - $3::text::interval)",
            plan.plan_id,
            DIGEST,
            age,
        )
        await cat_owner.execute(
            "insert into categories.apply_audit (mailbox_id, plan_id, message_id, old_label, new_label, channel) "
            "values ('mb1', $1, $2, 'a', 'b', 'web')",
            plan.plan_id,
            f"m{age}",
        )
        await cat_owner.execute(
            "update categories.apply_audit set at = now() - $1::text::interval where message_id = $2", age, f"m{age}"
        )

    counts = await _purge(cat_agent)

    assert (counts["plan_decision"], counts["plan_approval"], counts["apply_audit"]) == (1, 1, 1)
    for table in ("plan_decision", "plan_approval", "apply_audit"):
        assert await _count(cat_owner, table) == 1
        assert await _count(cat_owner, table, "at > now() - interval '1 year'") == 1


async def test_given_a_move_back_request_when_the_purge_runs_then_it_goes_after_a_year(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    old = await seed_plan(cat_owner, "mb1", state="applied", moves=(), tag="o")
    young = await seed_plan(cat_owner, "mb2", state="applied", moves=(), tag="y")
    for plan, age in ((old, "400 days"), (young, "300 days")):
        await cat_owner.execute(
            "insert into categories.move_back_request (mailbox_id, plan_id) values ($1, $2)", plan.mailbox, plan.plan_id
        )
        await cat_owner.execute(
            "update categories.move_back_request set at = now() - $1::text::interval where plan_id = $2",
            age,
            plan.plan_id,
        )

    await _purge(cat_agent)

    assert [r["plan_id"] for r in await cat_owner.fetch("select plan_id from categories.move_back_request")] == [
        young.plan_id
    ]


async def test_given_rejected_items_when_their_plan_is_purged_then_the_rejection_stays_until_the_list_changes(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await write_list(cat_owner, "mb1", 1, ["Bills"])
    plan = await seed_plan(cat_owner, state="ready", list_version=1)
    await cat_owner.execute(
        "insert into categories.rejection (mailbox_id, message_id, list_version) values ('mb1', 'm0', 1)"
    )
    await _age_plan(cat_owner, plan.plan_id, activity="15 days")

    await _purge(cat_agent)

    assert await _count(cat_owner, "plan_item") == 0
    assert await _count(cat_owner, "rejection") == 1
    await write_list(cat_owner, "mb1", 2, ["Bills", "Travel"])
    await _purge(cat_agent)
    assert await _count(cat_owner, "rejection") == 0


async def test_given_the_agent_when_it_supplies_a_session_clock_then_young_plan_rows_survive(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, state="ready")
    await _age_plan(cat_owner, plan.plan_id, activity="10 days")
    await cat_agent.execute("set timezone = 'Pacific/Kiritimati'")
    await cat_agent.execute(
        "create function pg_temp.now() returns timestamptz language sql as $$ select 'infinity'::timestamptz $$"
    )
    await cat_agent.execute("set search_path = pg_temp, public")

    counts = await _purge(cat_agent)

    assert counts["plan_item"] == 0
    assert await _count(cat_owner, "plan_item") == 5
