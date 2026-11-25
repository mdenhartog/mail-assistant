"""RED-001, SEC-001 and RED-006: the grants and triggers around the rename plan and the released labels (ADR-0061)."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from asyncpg import PostgresError

from tests.db.plan_support import sqlstate_of

if TYPE_CHECKING:
    import asyncpg

ITEM = (
    "insert into categories.label_rename_item (mailbox_id, label_id, old_name, new_name, mail_count, action) "
    "values ('mb1', 'L1', 'Assistant/Bills', 'Bills', 4, 'rename')"
)


async def _plan(owner: asyncpg.Connection, state: str) -> None:
    await owner.execute("insert into categories.label_migration (mailbox_id, state) values ('mb1', 'pending')")
    await owner.execute(ITEM)
    if state != "pending":  # the owner moves the state past the guard that only the definer function passes
        await owner.execute("alter table categories.label_migration disable trigger label_migration_guard")
        await owner.execute("update categories.label_migration set state = $1 where mailbox_id = 'mb1'", state)
        await owner.execute("alter table categories.label_migration enable trigger label_migration_guard")


@pytest.mark.parametrize(
    "statement",
    [
        "update categories.label_rename_item set new_name = 'Hacked' where label_id = 'L1'",
        "update categories.label_rename_item set old_name = 'x' where label_id = 'L1'",
        "update categories.label_rename_item set mail_count = 0 where label_id = 'L1'",
        "update categories.label_rename_item set action = 'merge' where label_id = 'L1'",
        "update categories.label_rename_item set label_id = 'L9' where label_id = 'L1'",
        "delete from categories.label_rename_item where label_id = 'L1'",
    ],
)
async def test_given_the_agent_role_when_it_rewrites_or_deletes_a_plan_item_then_the_grant_refuses(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, statement: str
) -> None:
    await _plan(cat_owner, "pending")

    with pytest.raises(PostgresError) as caught:
        await cat_agent.execute(statement)

    assert sqlstate_of(caught.value) == "42501"


async def test_given_the_agent_role_when_it_inserts_an_item_and_settles_its_state_then_it_works(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await cat_owner.execute("insert into categories.label_migration (mailbox_id, state) values ('mb1', 'pending')")
    await cat_agent.execute(ITEM)
    await cat_agent.execute("update categories.label_rename_item set state = 'skipped' where label_id = 'L1'")

    assert await cat_owner.fetchval("select state from categories.label_rename_item") == "skipped"


@pytest.mark.parametrize("state", ["confirmed", "done"])
@pytest.mark.parametrize("column", ["new_name", "old_name", "mail_count", "action", "label_id"])
async def test_given_a_plan_that_is_not_pending_when_any_role_changes_an_item_then_the_trigger_refuses(
    cat_owner: asyncpg.Connection, state: str, column: str
) -> None:
    await _plan(cat_owner, state)
    value = {"new_name": "'Other'", "old_name": "'x'", "mail_count": "9", "action": "'merge'", "label_id": "'L9'"}[
        column
    ]

    with pytest.raises(PostgresError) as caught:
        await cat_owner.execute(f"update categories.label_rename_item set {column} = {value}")  # noqa: S608

    assert sqlstate_of(caught.value) == "MC409"


async def test_given_a_pending_plan_when_the_owner_changes_an_item_then_it_is_allowed(
    cat_owner: asyncpg.Connection,
) -> None:
    await _plan(cat_owner, "pending")

    await cat_owner.execute("update categories.label_rename_item set new_name = 'Other'")


async def test_given_a_state_change_of_an_item_when_the_plan_is_confirmed_then_it_is_allowed(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _plan(cat_owner, "confirmed")

    await cat_agent.execute("update categories.label_rename_item set state = 'done' where label_id = 'L1'")


async def test_given_a_confirmed_plan_when_an_item_is_deleted_then_the_trigger_refuses(
    cat_owner: asyncpg.Connection,
) -> None:
    await _plan(cat_owner, "confirmed")

    with pytest.raises(PostgresError) as caught:
        await cat_owner.execute("delete from categories.label_rename_item")

    assert sqlstate_of(caught.value) == "MC409"


async def test_given_a_confirmed_plan_when_the_agent_purges_then_its_old_items_stay(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _plan(cat_owner, "confirmed")
    await cat_owner.execute(
        "update categories.label_rename_item set state = 'done', created_at = now() - interval '60 days'"
    )

    await cat_agent.fetchval("select categories.purge_label_records()")

    assert await cat_owner.fetchval("select count(*) from categories.label_rename_item") == 1


async def test_given_a_done_plan_when_the_agent_purges_old_items_then_they_go_without_a_delete_right(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _plan(cat_owner, "done")
    await cat_owner.execute(
        "update categories.label_rename_item set state = 'done', created_at = now() - interval '60 days'"
    )

    await cat_agent.fetchval("select categories.purge_label_records()")

    assert await cat_owner.fetchval("select count(*) from categories.label_rename_item") == 0


# --- RED-001: the record of a label that left management ---------------------------------------------------------


async def test_given_the_released_table_then_the_agent_has_full_dml_and_the_api_nothing(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await cat_owner.execute("insert into categories.mailbox (id) values ('mb1') on conflict do nothing")
    await cat_agent.execute("insert into categories.managed_label_released (mailbox_id, label_id) values ('mb1', 'L1')")
    await cat_agent.execute("update categories.managed_label_released set released_at = now()")
    assert await cat_agent.fetchval("select count(*) from categories.managed_label_released") == 1
    await cat_agent.execute("delete from categories.managed_label_released")
    with pytest.raises(PostgresError) as caught:
        await cat_api.fetch("select * from categories.managed_label_released")
    assert sqlstate_of(caught.value) == "42501"
