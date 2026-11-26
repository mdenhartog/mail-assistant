"""U-label-structure-23, criteria 2 and 6 on the real database: the apply store reads pairs and the extra labels.

Every test acts as the agent role. The owner seeds the list and the plan as ``approve_system_plan`` leaves them.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.core.judgement import OTHER_ID
from app.core.managed import LabelRef, ManagedLabel, Role
from app.db.pg_resort import PgApplyStore, PgBuildStore
from tests.db.plan_support import seed_plan
from tests.db.resort_support import MAILBOX, agent_sessions

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]


async def _list_with_an_extra(
    owner: asyncpg.Connection, *, names: tuple[str, str] | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    """A list of one topic (Finance) and one extra label (Newsletter); return their ids.

    ``names`` are the "Other" and the archive setting of the version; without them the defaults hold.
    """
    async with owner.transaction():  # categories may only be added in the transaction of their version
        await owner.execute("insert into categories.list_version (mailbox_id, version) values ($1, 1)", MAILBOX)
        if names is not None:
            await owner.execute(
                "insert into categories.list_settings (mailbox_id, version, other_label, archive_label) "
                "values ($1, 1, $2, $3)",
                MAILBOX,
                *names,
            )
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


async def test_given_a_list_with_an_extra_when_asked_then_the_managed_labels_carry_roles_names_and_stored_ids(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    topic, extra = await _list_with_an_extra(cat_owner)
    await cat_owner.execute(
        "insert into categories.managed_label (mailbox_id, label_id, role, category_id, label_name) "
        "values ($1, 'L_FIN', 'category', $2, 'Finance'), ($1, 'L_ARC', 'archive', null, 'Archive')",
        MAILBOX,
        topic,
    )

    labels = await PgApplyStore(agent_sessions, MAILBOX).managed_labels()

    assert labels.by_category[str(topic)] == ManagedLabel("Finance", "L_FIN", Role.TOPIC)
    assert labels.by_category[str(extra)] == ManagedLabel("Newsletter", None, Role.EXTRA)  # no id stored yet
    assert labels.by_category[OTHER_ID] == ManagedLabel("Other", None, Role.OTHER)  # the default of the setting
    assert labels.managed.archive == ManagedLabel("Archive", "L_ARC", Role.ARCHIVE)
    assert labels.managed.find(LabelRef("L_FIN", "renamed by hand")) == labels.by_category[str(topic)]
    assert labels.managed.find(LabelRef("L_X", "Newsletter")) == labels.by_category[str(extra)]  # by name, no id yet
    assert labels.managed.find(LabelRef("L_Y", "Amerika")) is None


async def test_given_the_other_and_archive_settings_when_asked_then_the_managed_labels_use_them(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    await _list_with_an_extra(cat_owner, names=("Everything else", "Done"))
    await cat_owner.execute(
        "insert into categories.managed_label (mailbox_id, label_id, role, category_id, label_name) "
        "values ($1, 'L_OTH', 'other', null, 'Other')",
        MAILBOX,
    )

    labels = await PgApplyStore(agent_sessions, MAILBOX).managed_labels()

    assert labels.by_category[OTHER_ID] == ManagedLabel("Everything else", "L_OTH", Role.OTHER)
    assert labels.managed.archive == ManagedLabel("Done", None, Role.ARCHIVE)


async def test_given_a_stored_label_of_a_category_that_left_the_list_when_asked_then_it_is_not_managed(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    await _list_with_an_extra(cat_owner)
    gone = uuid.uuid4()
    await cat_owner.execute("insert into categories.category_identity (mailbox_id, id) values ($1, $2)", MAILBOX, gone)
    await cat_owner.execute(
        "insert into categories.managed_label (mailbox_id, label_id, role, category_id, label_name) "
        "values ($1, 'L_OLD', 'category', $2, 'Old shop')",
        MAILBOX,
        gone,
    )

    labels = await PgBuildStore(agent_sessions, MAILBOX).managed_labels()

    assert labels.managed.find(LabelRef("L_OLD", "Old shop")) is None
    assert str(gone) not in labels.by_category


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
