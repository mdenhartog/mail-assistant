"""U-mail-categories-12, criterion 1 (AC-27): the rights on the plan tables are exactly the design matrix.

Written by hand from the design ("Grants and functions"): what is not listed is refused with SQLSTATE 42501.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.db.conftest import AGENT_ROLE, API_ROLE
from tests.db.plan_support import seed_plan

if TYPE_CHECKING:
    import asyncpg

ALL = "*"
ROLES = {"api": API_ROLE, "agent": AGENT_ROLE}
ITEM_API_COLUMNS = frozenset(
    {
        "mailbox_id",
        "plan_id",
        "id",
        "sender_name",
        "sender_address",
        "subject",
        "old_category_id",
        "new_category_id",
        "decision",
        "state",
        "reason",
    }
)
ITEM_AGENT_INSERT = frozenset(
    {
        "mailbox_id",
        "plan_id",
        "message_id",
        "sender_name",
        "sender_address",
        "subject",
        "old_category_id",
        "new_category_id",
    }
)
NONE: frozenset[str] = frozenset()
# table -> role -> (select, insert, update) columns; ALL means every column
MATRIX: dict[str, dict[str, tuple[frozenset[str] | str, frozenset[str] | str, frozenset[str] | str]]] = {
    "plan": {"api": (ALL, NONE, NONE), "agent": (ALL, ALL, ALL)},
    "plan_item": {
        "api": (ITEM_API_COLUMNS, NONE, NONE),
        "agent": (ALL, ITEM_AGENT_INSERT, frozenset({"state", "reason", "attempts"})),
    },
    "plan_decision": {"api": (NONE, NONE, NONE), "agent": (ALL, NONE, NONE)},
    "plan_approval": {"api": (NONE, NONE, NONE), "agent": (ALL, NONE, NONE)},
    "apply_audit": {
        "api": (NONE, NONE, NONE),
        "agent": (
            ALL,
            frozenset({"mailbox_id", "plan_id", "message_id", "old_label", "new_label", "channel", "kind"}),
            NONE,
        ),
    },
    "move_back_request": {
        "api": (ALL, frozenset({"mailbox_id", "plan_id"}), NONE),
        "agent": (ALL, frozenset({"mailbox_id", "plan_id"}), frozenset({"processed", "run_id", "lease_until"})),
    },
}


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("table", MATRIX)
async def test_given_the_matrix_when_the_catalog_is_asked_then_every_plan_column_privilege_is_exactly_the_listed_one(
    cat_owner: asyncpg.Connection, table: str, role: str
) -> None:
    columns = [
        r["column_name"]
        for r in await cat_owner.fetch(
            "select column_name from information_schema.columns where table_schema = 'categories' and table_name = $1",
            table,
        )
    ]
    target = f"categories.{table}"
    for operation, allowed in zip(("SELECT", "INSERT", "UPDATE"), MATRIX[table][role], strict=True):
        expected = frozenset(columns) if allowed == ALL else allowed
        for column in columns:
            actual = await cat_owner.fetchval(
                "select has_column_privilege($1, $2, $3, $4)", ROLES[role], target, column, operation
            )
            assert actual == (column in expected), (table, role, operation, column)
    for privilege in ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        actual = await cat_owner.fetchval("select has_table_privilege($1, $2, $3)", ROLES[role], target, privilege)
        assert actual is False, (table, role, privilege)


async def _sqlstate(connection: asyncpg.Connection, statement: str, *args: object) -> str | None:
    import asyncpg as driver  # noqa: PLC0415  # only the error type is needed at run time

    try:
        await connection.execute(statement, *args)
    except driver.PostgresError as error:
        return str(error.sqlstate)  # pyright: ignore[reportAttributeAccessIssue]  # asyncpg types it on subclasses
    return None


async def test_given_the_api_role_when_it_writes_items_decisions_approvals_or_audit_directly_then_42501(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)
    statements = (
        "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
        "old_category_id, new_category_id) values ('mb1', $1, 'x', 'n', 'a', 's', $1, $1)",
        "update categories.plan_item set decision = 'approved' where plan_id = $1",
        "update categories.plan_item set state = 'approved' where plan_id = $1",
        "delete from categories.plan_item where plan_id = $1",
        "update categories.plan set state = 'scheduled' where id = $1",
        "insert into categories.plan_decision (mailbox_id, plan_id, scope, item_count, decision, channel, "
        "actor_digest) values ('mb1', $1, 'all', 1, 'approved', 'web', repeat('a', 64))",
        "insert into categories.plan_approval (mailbox_id, plan_id, approved_count, channel, actor_digest) "
        "values ('mb1', $1, 1, 'web', repeat('a', 64))",
        "insert into categories.apply_audit (mailbox_id, plan_id, message_id, old_label, new_label, channel, "
        "actor_digest) values ('mb1', $1, 'm', 'a', 'b', 'web', repeat('a', 64))",
        "delete from categories.plan_decision",
        "update categories.plan_approval set approved_count = 0",
        "create table categories.evil (id int)",
    )

    for statement in statements:
        needs_id = "$1" in statement
        state = await (_sqlstate(cat_api, statement, plan.plan_id) if needs_id else _sqlstate(cat_api, statement))
        assert state == "42501", statement


async def test_given_the_agent_role_when_it_changes_a_decision_or_deletes_audit_data_then_42501(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner)

    for statement in (
        "update categories.plan_item set decision = 'approved' where plan_id = $1",
        "delete from categories.plan_item where plan_id = $1",
        "delete from categories.apply_audit where plan_id = $1",
        "delete from categories.plan_decision where plan_id = $1",
        "delete from categories.plan_approval where plan_id = $1",
        "delete from categories.move_back_request where plan_id = $1",
        "update categories.apply_audit set new_label = 'x' where plan_id = $1",
    ):
        assert await _sqlstate(cat_agent, statement, plan.plan_id) == "42501", statement
