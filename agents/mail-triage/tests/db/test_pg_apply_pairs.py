"""U-label-structure-23, criteria 2 and 6 on the real database: the apply store reads pairs and the extra labels.

Every test acts as the agent role. The owner seeds the list and the plan as ``approve_system_plan`` leaves them.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.db.pg_resort import PgApplyStore
from tests.db.plan_support import seed_plan
from tests.db.resort_support import MAILBOX, agent_sessions

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]


async def _list_with_an_extra(owner: asyncpg.Connection) -> tuple[uuid.UUID, uuid.UUID]:
    """A list of one topic (Finance) and one extra label (Newsletter); return their ids."""
    async with owner.transaction():  # categories may only be added in the transaction of their version
        await owner.execute("insert into categories.list_version (mailbox_id, version) values ($1, 1)", MAILBOX)
        ids: list[uuid.UUID] = []
        for position, (name, kind) in enumerate((("Finance", "topic"), ("Newsletter", "extra"))):
            identity = uuid.uuid4()
            ids.append(identity)
            await owner.execute(
                "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", MAILBOX, identity
            )
            await owner.execute(
                "insert into categories.category (mailbox_id, version, id, name, description, position, kind) "
                "values ($1, 1, $2, $3, 'about it', $4, $5)",
                MAILBOX,
                identity,
                name,
                position,
                kind,
            )
    return ids[0], ids[1]


async def test_given_a_pair_item_when_read_for_the_apply_then_it_carries_both_pairs(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    topic, extra = await _list_with_an_extra(cat_owner)
    plan = await seed_plan(cat_owner, moves=((uuid.UUID(int=0), topic),))
    await cat_owner.execute(
        "update categories.plan_item set old_topic_id = $1, old_extra_id = null, new_topic_id = $2, new_extra_id = $3, "
        "decision = 'approved', state = 'approved' where plan_id = $4",
        uuid.UUID(int=0),
        topic,
        extra,
        plan.plan_id,
    )

    [one] = await PgApplyStore(agent_sessions, MAILBOX).next_items(plan.plan_id, 10)

    assert (one.old_topic_id, one.old_extra_id, one.new_topic_id, one.new_extra_id) == (
        uuid.UUID(int=0),
        None,
        topic,
        extra,
    )


async def test_given_an_item_of_an_older_plan_when_read_then_the_topic_columns_stand_in_for_the_pair(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan = await seed_plan(cat_owner, moves=((uuid.UUID(int=1), uuid.UUID(int=2)),))  # no pair columns
    await cat_owner.execute("update categories.plan_item set decision = 'approved', state = 'approved'")

    [one] = await PgApplyStore(agent_sessions, MAILBOX).next_items(plan.plan_id, 10)

    assert (one.old_topic_id, one.new_topic_id, one.old_extra_id, one.new_extra_id) == (
        uuid.UUID(int=1),
        uuid.UUID(int=2),
        None,
        None,
    )


async def test_given_a_list_with_an_extra_when_asked_then_the_extra_label_names_are_returned(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    await _list_with_an_extra(cat_owner)

    assert await PgApplyStore(agent_sessions, MAILBOX).extra_label_names() == {"Assistant/Newsletter"}


async def test_given_approved_items_when_the_targets_are_asked_then_only_the_open_ones_count(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    topic, extra = await _list_with_an_extra(cat_owner)
    plan = await seed_plan(cat_owner, moves=((uuid.UUID(int=0), topic), (uuid.UUID(int=0), uuid.UUID(int=9))))
    await cat_owner.execute(
        "update categories.plan_item set new_topic_id = new_category_id, decision = 'approved', state = 'approved'"
    )
    await cat_owner.execute(
        "update categories.plan_item set new_extra_id = $1 where plan_id = $2 and message_id = 'm0'",
        extra,
        plan.plan_id,
    )
    store = PgApplyStore(agent_sessions, MAILBOX)

    assert await store.target_ids(plan.plan_id) == {str(topic), str(extra), str(uuid.UUID(int=9))}

    # an item that was applied is no longer a target
    await cat_owner.execute(
        "update categories.plan_item set state = 'applied' where plan_id = $1 and message_id = 'm1'", plan.plan_id
    )
    assert await store.target_ids(plan.plan_id) == {str(topic), str(extra)}
