"""U-mail-categories-22: migration 0018 makes the apply and the build safe to run from two processes and to retry.

It adds the lease of an apply run on the plan and of a move-back request, the attempt counter of an item, the kind of an
audit row (apply or restore: the move back reads only the apply rows) and two SECURITY DEFINER functions, because the
agent role has no DELETE right on ``plan_item`` (ADR-0047): ``replace_plan`` and ``remove_applied_items``.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import uuid

import asyncpg
from alembic import command

from tests.db.conftest import AGENT_ROLE, API_ROLE, alembic_config, plain_url

_NEW_COLUMNS = {
    ("plan", "apply_run_id"),
    ("plan", "apply_lease_until"),
    ("plan_item", "attempts"),
    ("move_back_request", "run_id"),
    ("move_back_request", "lease_until"),
    ("apply_audit", "kind"),
}
_FUNCTIONS = ("replace_plan(text, uuid)", "remove_applied_items(text, uuid)")


async def _columns(connection: asyncpg.Connection) -> set[tuple[str, str]]:
    rows = await connection.fetch(
        "select table_name, column_name from information_schema.columns where table_schema = 'categories'"
    )
    return {(r["table_name"], r["column_name"]) for r in rows}


async def _functions(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch(
        "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'categories' and p.proname in ('replace_plan', 'remove_applied_items')"
    )
    return {r["proname"] for r in rows}


async def test_given_0018_when_run_up_down_and_up_then_the_columns_and_functions_come_go_and_come_back(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0017")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        assert not _NEW_COLUMNS & await _columns(connection)
        plan_id = uuid.uuid4()
        await connection.execute("insert into categories.mailbox (id) values ('mb1')")
        await connection.execute(
            "insert into categories.apply_audit (mailbox_id, plan_id, message_id, old_label, new_label, channel) "
            "values ('mb1', $1, 'm1', 'Label_1', 'Label_2', 'web')",
            plan_id,
        )

        await asyncio.to_thread(command.upgrade, config, "0018")

        assert _NEW_COLUMNS <= await _columns(connection)
        assert await _functions(connection) == {"replace_plan", "remove_applied_items"}
        assert await connection.fetchval("select kind from categories.apply_audit") == "apply"  # old rows are applies

        await asyncio.to_thread(command.downgrade, config, "0017")

        assert not _NEW_COLUMNS & await _columns(connection)
        assert await _functions(connection) == set()
        assert await connection.fetchval("select count(*) from categories.apply_audit") == 1  # the data stays

        await asyncio.to_thread(command.upgrade, config, "0018")

        assert _NEW_COLUMNS <= await _columns(connection)
    finally:
        await connection.close()


async def test_given_the_new_functions_then_only_the_agent_may_run_them_and_the_definer_owns_them(
    cat_owner: asyncpg.Connection,
) -> None:
    for function in _FUNCTIONS:
        target = f"categories.{function}"
        assert await cat_owner.fetchval("select has_function_privilege($1, $2, 'EXECUTE')", AGENT_ROLE, target)
        assert not await cat_owner.fetchval("select has_function_privilege($1, $2, 'EXECUTE')", API_ROLE, target)
        owner = await cat_owner.fetchval("select proowner::regrole::text from pg_proc where oid = $1::regprocedure", target)
        assert owner == "categories_definer"
