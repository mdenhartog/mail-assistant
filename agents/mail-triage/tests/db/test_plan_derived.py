"""U-mail-categories-12, contract: the apply audit and the move-back request derive actor and time in the database."""

from __future__ import annotations

import hashlib
import uuid

import asyncpg
import pytest

from tests.db.conftest import AGENT_ROLE, API_ROLE
from tests.db.plan_support import seed_plan


def _digest(role: str) -> str:
    return hashlib.sha256(role.encode()).hexdigest()


async def test_given_the_agent_when_it_appends_an_apply_audit_row_then_the_database_derives_actor_and_time(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, state="applying")

    await cat_agent.execute(
        "insert into categories.apply_audit (mailbox_id, plan_id, message_id, old_label, new_label, channel) "
        "values ('mb1', $1, 'm0', 'Assistant/A', 'Assistant/B', 'web')",
        plan.plan_id,
    )

    row = await cat_owner.fetchrow(
        "select actor_digest, channel, at <= now() and at > now() - interval '1 minute' as fresh "
        "from categories.apply_audit"
    )
    assert row is not None
    assert row["actor_digest"] == _digest(AGENT_ROLE)
    assert row["channel"] == "web"
    assert row["fresh"] is True


async def test_given_an_unknown_channel_when_the_agent_appends_an_apply_audit_row_then_it_is_refused(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, state="applying")

    with pytest.raises(asyncpg.CheckViolationError):
        await cat_agent.execute(
            "insert into categories.apply_audit (mailbox_id, plan_id, message_id, old_label, new_label, channel) "
            "values ('mb1', $1, 'm0', 'a', 'b', 'carrier-pigeon')",
            plan.plan_id,
        )


async def test_given_an_applied_plan_when_the_api_asks_to_move_back_then_the_request_is_stored_once_with_its_actor(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, state="applied", moves=())

    await cat_api.execute(
        "insert into categories.move_back_request (mailbox_id, plan_id) values ('mb1', $1)", plan.plan_id
    )

    row = await cat_owner.fetchrow("select actor_digest, processed from categories.move_back_request")
    assert row is not None
    assert row["actor_digest"] == _digest(API_ROLE)
    assert row["processed"] is False
    with pytest.raises(asyncpg.UniqueViolationError):
        await cat_api.execute(
            "insert into categories.move_back_request (mailbox_id, plan_id) values ('mb1', $1)", plan.plan_id
        )


@pytest.mark.parametrize("state", ["building", "ready", "scheduled", "applying", "cancelled", "replaced"])
async def test_given_a_plan_that_is_not_applied_when_the_api_asks_to_move_back_then_409(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, state: str
) -> None:
    plan = await seed_plan(cat_owner, state=state, moves=())

    with pytest.raises(asyncpg.PostgresError) as error:
        await cat_api.execute(
            "insert into categories.move_back_request (mailbox_id, plan_id) values ('mb1', $1)", plan.plan_id
        )

    assert error.value.sqlstate == "MC409"


async def test_given_a_plan_of_another_mailbox_or_none_when_the_api_asks_to_move_back_then_409(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    other = await seed_plan(cat_owner, "mb2", state="applied", moves=())

    for mailbox, plan_id in (("mb1", other.plan_id), ("mb1", uuid.uuid4())):
        with pytest.raises(asyncpg.PostgresError) as error:
            await cat_api.execute(
                "insert into categories.move_back_request (mailbox_id, plan_id) values ($1, $2)", mailbox, plan_id
            )
        assert error.value.sqlstate == "MC409"
