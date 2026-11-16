"""RED-006: only ``approve_plan`` schedules a plan or sets ``apply_after``; the agent role cannot (ADR-0046, ADR-0047).

The agent writes plans (state, progress, lease, ``announced_at``) but must not move ``ready`` to ``scheduled`` or
lower ``apply_after``: that would skip the approval, the threshold and the delay. The rights refuse it (42501) and, as
a second line, a trigger refuses it for any role that is not the definer (or the owner).
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncpg
import pytest

from tests.db.plan_support import seed_plan
from tests.db.test_pg_resort_apply import scheduled_plan

REFUSED = "42501"


async def _sqlstate(connection: asyncpg.Connection, statement: str, *args: object) -> str | None:
    try:
        await connection.execute(statement, *args)
    except asyncpg.PostgresError as error:
        return str(error.sqlstate)  # pyright: ignore[reportAttributeAccessIssue]  # asyncpg types it on subclasses
    return None


async def test_given_a_ready_plan_when_the_agent_schedules_it_directly_then_42501(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, state="ready")

    state = await _sqlstate(
        cat_agent, "update categories.plan set state = 'scheduled', apply_after = now() where id = $1", plan.plan_id
    )

    assert state == REFUSED
    assert await cat_owner.fetchval("select state from categories.plan") == "ready"


async def test_given_a_scheduled_plan_when_the_agent_lowers_apply_after_then_42501(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan_id = await scheduled_plan(cat_owner)
    await cat_owner.execute("update categories.plan set apply_after = now() + interval '15 minutes'")

    state = await _sqlstate(cat_agent, "update categories.plan set apply_after = now() where id = $1", plan_id)

    assert state == REFUSED


async def test_given_the_agent_role_when_it_inserts_a_scheduled_plan_then_42501(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await cat_owner.execute("insert into categories.list_version (mailbox_id, version) values ('mb1', 1)")

    state = await _sqlstate(
        cat_agent,
        "insert into categories.plan (mailbox_id, list_version, state, apply_after) "
        "values ('mb1', 1, 'scheduled', now())",
    )

    assert state == REFUSED


@pytest.mark.parametrize(
    "statement",
    [
        "update categories.plan set state = 'scheduled', apply_after = now() where id = $1",
        "update categories.plan set apply_after = now() - interval '1 hour' where id = $1",
    ],
)
async def test_given_a_column_right_when_a_role_that_is_not_the_definer_schedules_then_the_trigger_refuses(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, statement: str
) -> None:
    """The second line: even with the column right, the trigger refuses (the rights are the first line)."""
    plan = await seed_plan(cat_owner, state="ready")
    await cat_owner.execute("grant update (apply_after) on categories.plan to mail_triage_runtime")

    state = await _sqlstate(cat_agent, statement, plan.plan_id)

    assert state == REFUSED
    assert await cat_owner.fetchval("select state from categories.plan") == "ready"
