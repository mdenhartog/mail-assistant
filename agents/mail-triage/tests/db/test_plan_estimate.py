"""U-mail-categories-14, decision from U-17: the plan keeps the estimate of mail in scope and not-looked-at.

The review page shows "N of about M checked" and "not looked at" (D15); the api reads both from the plan row.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from alembic import command

from tests.db.conftest import alembic_config, plain_url
from tests.db.plan_support import seed_plan, sqlstate_of

COLUMNS = "select column_name from information_schema.columns where table_schema='categories' and table_name='plan'"


async def test_given_a_new_plan_then_the_estimate_is_unknown_and_nothing_is_unlooked(
    cat_owner: asyncpg.Connection,
) -> None:
    plan = await seed_plan(cat_owner)

    row = await cat_owner.fetchrow(
        "select estimate_total, not_looked_at from categories.plan where id = $1", plan.plan_id
    )

    assert row is not None
    assert (row["estimate_total"], row["not_looked_at"]) == (None, 0)


async def test_given_negative_counts_then_the_database_refuses_them(cat_owner: asyncpg.Connection) -> None:
    plan = await seed_plan(cat_owner)

    for column in ("estimate_total", "not_looked_at"):
        with pytest.raises(asyncpg.PostgresError) as caught:
            await cat_owner.execute(f"update categories.plan set {column} = -1 where id = $1", plan.plan_id)  # noqa: S608
        assert sqlstate_of(caught.value) == "23514"


async def test_given_the_roles_then_the_agent_writes_both_counts_and_the_api_reads_them(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan = await seed_plan(cat_owner, state="building")

    await cat_agent.execute(
        "update categories.plan set estimate_total = 5200, not_looked_at = 200 where id = $1", plan.plan_id
    )

    row = await cat_api.fetchrow(
        "select estimate_total, not_looked_at from categories.plan where id = $1", plan.plan_id
    )
    assert row is not None
    assert (row["estimate_total"], row["not_looked_at"]) == (5200, 200)
    with pytest.raises(asyncpg.PostgresError) as caught:
        await cat_api.execute("update categories.plan set not_looked_at = 0 where id = $1", plan.plan_id)
    assert sqlstate_of(caught.value) == "42501"


async def test_given_the_revision_when_it_goes_down_then_the_columns_go_and_the_plan_stays(database_url: str) -> None:
    async def columns() -> set[str]:
        connection = await asyncpg.connect(plain_url(database_url))
        try:
            return {r["column_name"] for r in await connection.fetch(COLUMNS)}
        finally:
            await connection.close()

    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "head")
    assert {"estimate_total", "not_looked_at"} <= await columns()

    await asyncio.to_thread(command.downgrade, alembic_config(database_url), "0015")
    after_down = await columns()
    assert not {"estimate_total", "not_looked_at"} & after_down
    assert "checked_count" in after_down

    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "head")
    assert {"estimate_total", "not_looked_at"} <= await columns()
