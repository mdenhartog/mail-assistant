"""U-mail-categories-12, criterion 6 (AC-42): Cancel and the start of the apply race; exactly one wins.

Both are compare-and-set updates under the plan's row lock, run by the agent (ADR-0046); the state guard of the
database refuses any other move.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from tests.db.conftest import connect_as
from tests.db.plan_support import seed_plan

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

CANCEL = "update categories.plan set state = 'cancelled' where mailbox_id = 'mb1' and id = $1 and state = 'scheduled'"
START = (
    "update categories.plan set state = 'applying' "
    "where mailbox_id = 'mb1' and id = $1 and state = 'scheduled' and apply_after <= now()"
)


@pytest.fixture
async def second_agent(cat_url: str, cat_owner: asyncpg.Connection) -> AsyncIterator[asyncpg.Connection]:
    """A second connection of the agent role."""
    connection = await connect_as(cat_url, "mail_triage_runtime")
    yield connection
    await connection.close()


async def _scheduled(owner: asyncpg.Connection) -> asyncpg.Record:
    plan = await seed_plan(owner, state="scheduled", moves=())
    await owner.execute(
        "update categories.plan set apply_after = now() - interval '1 minute' where id = $1", plan.plan_id
    )
    return await owner.fetchrow("select id from categories.plan where id = $1", plan.plan_id)  # type: ignore[return-value]


async def test_given_cancel_commits_first_when_the_start_of_the_apply_follows_then_it_changes_nothing(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, second_agent: asyncpg.Connection
) -> None:
    plan = await _scheduled(cat_owner)
    transaction = cat_agent.transaction()
    await transaction.start()
    assert await cat_agent.execute(CANCEL, plan["id"]) == "UPDATE 1"

    start = asyncio.create_task(second_agent.execute(START, plan["id"]))
    await asyncio.sleep(0.3)
    assert not start.done()  # the start waits for the row lock of the cancel
    await transaction.commit()

    assert await start == "UPDATE 0"
    assert await cat_owner.fetchval("select state from categories.plan where id = $1", plan["id"]) == "cancelled"


async def test_given_the_start_commits_first_when_cancel_follows_then_cancel_changes_nothing_of_the_scheduled_state(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, second_agent: asyncpg.Connection
) -> None:
    plan = await _scheduled(cat_owner)
    transaction = cat_agent.transaction()
    await transaction.start()
    assert await cat_agent.execute(START, plan["id"]) == "UPDATE 1"

    cancel = asyncio.create_task(second_agent.execute(CANCEL, plan["id"]))
    await asyncio.sleep(0.3)
    assert not cancel.done()
    await transaction.commit()

    assert await cancel == "UPDATE 0"
    assert await cat_owner.fetchval("select state from categories.plan where id = $1", plan["id"]) == "applying"


async def test_given_many_plans_when_cancel_and_start_run_at_the_same_time_then_exactly_one_wins_each_time(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, second_agent: asyncpg.Connection
) -> None:
    for _ in range(25):
        plan = await _scheduled(cat_owner)

        cancelled, started = await asyncio.gather(
            cat_agent.execute(CANCEL, plan["id"]), second_agent.execute(START, plan["id"])
        )

        assert sorted([cancelled, started]) == ["UPDATE 0", "UPDATE 1"]
        final = await cat_owner.fetchval("select state from categories.plan where id = $1", plan["id"])
        assert final == ("cancelled" if cancelled == "UPDATE 1" else "applying")
        await cat_owner.execute(
            "update categories.plan set state = 'cancelled' where id = $1 and state = 'applying'", plan["id"]
        )
