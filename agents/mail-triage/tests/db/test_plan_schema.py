"""U-mail-categories-12, contract: the plan revision (tables, one open plan per mailbox, legal state moves).

The legal moves of the database are compared with the pure state machine ``app.core.resort_plan`` (ADR-0046).
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from alembic import command

from app.core.resort_plan import InvalidTransitionError, PlanEvent, PlanState, transition
from tests.db.conftest import alembic_config, plain_url
from tests.db.plan_support import seed_plan

PLAN_TABLES = {"plan", "plan_item", "plan_decision", "plan_approval", "apply_audit", "move_back_request"}
TERMINAL = {"applied", "replaced", "discarded", "cancelled"}


async def _sqlstate(connection: asyncpg.Connection, statement: str, *args: object) -> str | None:
    try:
        await connection.execute(statement, *args)
    except asyncpg.PostgresError as error:
        return str(error.sqlstate)  # pyright: ignore[reportAttributeAccessIssue]  # asyncpg types it on subclasses
    return None


async def test_given_the_plan_revision_when_it_goes_up_and_down_then_only_the_plan_tables_come_and_go(
    database_url: str,
) -> None:
    async def tables() -> set[str]:
        connection = await asyncpg.connect(plain_url(database_url))
        try:
            rows = await connection.fetch(
                "select table_name from information_schema.tables where table_schema = 'categories'"
            )
        finally:
            await connection.close()
        return {r["table_name"] for r in rows}

    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "head")
    assert await tables() >= PLAN_TABLES

    await asyncio.to_thread(command.downgrade, alembic_config(database_url), "0014")
    after_down = await tables()
    assert not PLAN_TABLES & after_down
    assert "list_version" in after_down  # the list half stays

    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "head")
    assert await tables() >= PLAN_TABLES


async def test_given_every_plan_table_when_its_primary_key_is_read_then_the_mailbox_id_comes_first(
    cat_owner: asyncpg.Connection,
) -> None:
    rows = await cat_owner.fetch(
        "select c.relname as t, (select a.attname from pg_attribute a where a.attrelid = c.oid "
        "and a.attnum = i.indkey[0]) as first_column "
        "from pg_index i join pg_class c on c.oid = i.indrelid join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'categories' and i.indisprimary and c.relname = any($1::text[])",
        sorted(PLAN_TABLES),
    )

    assert {r["t"]: r["first_column"] for r in rows} == dict.fromkeys(PLAN_TABLES, "mailbox_id")


async def test_given_an_open_plan_when_a_second_open_plan_is_made_then_the_unique_index_refuses_it(
    cat_owner: asyncpg.Connection,
) -> None:
    await seed_plan(cat_owner, "mb1", state="building", tag="a")

    assert (
        await _sqlstate(
            cat_owner,
            "insert into categories.plan (mailbox_id, id, list_version, state) values ('mb1', $1, 1, 'ready')",
            uuid.uuid4(),
        )
        == "23505"
    )
    # another mailbox, and a terminal plan, are not blocked
    await seed_plan(cat_owner, "mb2", state="ready", tag="b")
    for state in sorted(TERMINAL):
        await seed_plan(cat_owner, "mb1", state=state, tag=state)


async def test_given_the_open_plan_ends_when_a_new_plan_is_made_then_it_is_allowed(
    cat_owner: asyncpg.Connection,
) -> None:
    first = await seed_plan(cat_owner, "mb1", state="building", tag="a")
    await cat_owner.execute(
        "update categories.plan set state = 'replaced' where mailbox_id = 'mb1' and id = $1", first.plan_id
    )

    await seed_plan(cat_owner, "mb1", state="building", tag="b")


def _legal_moves() -> set[tuple[str, str]]:
    legal: set[tuple[str, str]] = set()
    for state in PlanState:
        for event in PlanEvent:
            try:
                legal.add((state.value, transition(state, event).value))
            except InvalidTransitionError:
                continue
    return legal


@pytest.mark.parametrize("old", [s.value for s in PlanState])
@pytest.mark.parametrize("new", [s.value for s in PlanState])
async def test_given_a_plan_state_when_it_moves_then_the_database_allows_exactly_the_moves_of_the_state_machine(
    cat_owner: asyncpg.Connection, old: str, new: str
) -> None:
    if old == new:
        pytest.skip("not a move")
    plan = await seed_plan(cat_owner, "mb1", state=old, moves=())

    state = await _sqlstate(
        cat_owner,
        "update categories.plan set state = $2 where mailbox_id = 'mb1' and id = $1",
        plan.plan_id,
        new,
    )

    assert (state is None) == ((old, new) in _legal_moves()), (old, new, state)
    if state is not None:
        assert state == "MC409"


async def test_given_a_plan_that_ends_when_its_state_is_set_then_the_database_stamps_the_end_time(
    cat_owner: asyncpg.Connection,
) -> None:
    plan = await seed_plan(cat_owner, "mb1", state="scheduled", moves=())
    before = await cat_owner.fetchval(
        "select terminal_at from categories.plan where mailbox_id = 'mb1' and id = $1", plan.plan_id
    )
    assert before is None

    await cat_owner.execute(
        "update categories.plan set state = 'cancelled' where mailbox_id = 'mb1' and id = $1", plan.plan_id
    )

    assert (
        await cat_owner.fetchval(
            "select terminal_at is not null from categories.plan where mailbox_id = 'mb1' and id = $1", plan.plan_id
        )
        is True
    )
