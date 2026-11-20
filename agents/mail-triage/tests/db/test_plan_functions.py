"""U-mail-categories-12, criterion 9 (AC-56): owner, search_path, PUBLIC and EXECUTE of the decision functions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from tests.db.conftest import AGENT_ROLE, API_ROLE
from tests.db.plan_support import CAT_A, NIL, scope_all, seed_plan, set_apply_config

if TYPE_CHECKING:
    import asyncpg

DECISION_FUNCTIONS = {
    "record_decision": "categories.record_decision(text, uuid, integer, jsonb, text)",
    "approve_plan": "categories.approve_plan(text, uuid, integer)",
}
PURGE = "categories.purge_expired()"
DEFINER = "categories_definer"


async def _can(owner: asyncpg.Connection, role: str, function: str) -> bool:
    return bool(await owner.fetchval("select has_function_privilege($1, $2, 'EXECUTE')", role, function))


@pytest.mark.parametrize("function", [*DECISION_FUNCTIONS.values(), PURGE])
async def test_given_a_definer_function_when_its_catalog_row_is_read_then_it_is_a_pinned_definer_of_a_non_login_role(
    cat_owner: asyncpg.Connection, function: str
) -> None:
    row = await cat_owner.fetchrow(
        "select p.prosecdef, p.proconfig, r.rolname, r.rolcanlogin, r.rolsuper "
        "from pg_proc p join pg_roles r on r.oid = p.proowner where p.oid = $1::regprocedure",
        function,
    )

    assert row is not None
    assert row["prosecdef"] is True
    assert "search_path=pg_catalog, pg_temp" in row["proconfig"]
    assert (row["rolname"], row["rolcanlogin"], row["rolsuper"]) == (DEFINER, False, False)


async def test_given_the_categories_schema_when_every_function_is_listed_then_each_has_the_non_login_owner_and_a_path(
    cat_owner: asyncpg.Connection,
) -> None:
    rows = await cat_owner.fetch(
        "select p.proname, r.rolname, p.proconfig from pg_proc p join pg_roles r on r.oid = p.proowner "
        "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'categories'"
    )

    assert len(rows) >= 12
    for row in rows:
        assert row["rolname"] == DEFINER, row["proname"]
        assert row["proconfig"] is not None
        assert any(setting.startswith("search_path=pg_catalog") for setting in row["proconfig"]), row["proname"]


async def test_given_the_categories_functions_when_execute_rights_are_read_then_only_the_planned_roles_have_them(
    cat_owner: asyncpg.Connection,
) -> None:
    rows = await cat_owner.fetch(
        "select p.oid::regprocedure::text as signature from pg_proc p "
        "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'categories'"
    )
    assert rows
    for row in rows:
        assert not await _can(cat_owner, "public", row["signature"]), row["signature"]

    for function in DECISION_FUNCTIONS.values():
        assert await _can(cat_owner, API_ROLE, function)
        assert not await _can(cat_owner, AGENT_ROLE, function)
    assert await _can(cat_owner, AGENT_ROLE, PURGE)
    assert not await _can(cat_owner, API_ROLE, PURGE)


async def test_given_the_function_sources_when_they_are_read_then_no_sql_is_built_from_an_argument(
    cat_owner: asyncpg.Connection,
) -> None:
    rows = await cat_owner.fetch(
        "select p.proname, p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'categories' and p.prolang = (select oid from pg_language where lanname = 'plpgsql')"
    )

    assert rows
    for row in rows:
        source = re.sub(r"--[^\n]*", "", row["prosrc"])  # a comment may say the word
        assert not re.search(r"\bEXECUTE\b", source, re.IGNORECASE), row["proname"]
        assert "format(" not in source.lower(), row["proname"]
        assert "||" not in source or "jsonb" in source.lower(), row["proname"]  # only purge joins json results


async def test_given_the_api_when_it_calls_the_functions_with_a_hostile_search_path_then_the_pinned_one_wins(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await set_apply_config(cat_owner, threshold=1, delay_minutes=15)
    plan = await seed_plan(cat_owner, moves=((NIL, CAT_A),) * 3)
    await cat_api.execute(
        "create function pg_temp.now() returns timestamptz language sql as $$ select 'infinity'::timestamptz $$"
    )
    await cat_api.execute("create temp table plan_item (id int)")
    await cat_api.execute("set search_path = pg_temp, public")
    await cat_api.execute("set timezone = 'Pacific/Kiritimati'")

    await cat_api.fetchval(
        "select categories.record_decision($1, $2, 3, $3::jsonb, 'approved')", plan.mailbox, plan.plan_id, scope_all()
    )
    row = await cat_api.fetchrow("select * from categories.approve_plan($1, $2, 3)", plan.mailbox, plan.plan_id)

    assert row is not None
    assert row["apply_after"].isoformat() != "infinity"
    stored = await cat_owner.fetchval(
        "select count(*) from categories.plan_item where plan_id = $1 and state = 'approved'", plan.plan_id
    )
    assert stored == 3
