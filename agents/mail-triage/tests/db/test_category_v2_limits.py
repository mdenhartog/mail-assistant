"""U-label-structure-31: the category checks follow the v2 limits of category-policy."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import re
import uuid

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.db.conftest import alembic_config, plain_url

PREVIOUS = "0022"
_INSERT = (
    "insert into categories.category (mailbox_id, version, id, name, description, position) "
    "values ($1, $2, $3, $4, $5, $6)"
)


async def _add(
    connection: asyncpg.Connection, version: int, name: str, description: str = "d", position: int = 0
) -> None:
    """One list version with one category, written by the owner in one transaction."""
    identity = uuid.uuid4()
    async with connection.transaction():
        await connection.execute("insert into categories.mailbox (id) values ('mb') on conflict do nothing")
        await connection.execute("insert into categories.list_version (mailbox_id, version) values ('mb', $1)", version)
        await connection.execute(
            "insert into categories.category_identity (mailbox_id, id) values ('mb', $1)", identity
        )
        await connection.execute(_INSERT, "mb", version, identity, name, description, position)


async def _up(url: str, revision: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), revision)


async def _down(url: str, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(url), revision)


async def _definitions(connection: asyncpg.Connection) -> dict[str, str]:
    rows = await connection.fetch(
        "select conname, pg_get_constraintdef(oid) as d from pg_constraint "
        "where conrelid = 'categories.category'::regclass and contype = 'c'"
    )
    return {r["conname"]: r["d"] for r in rows}


def _numbers(definition: str) -> list[int]:
    """The limits in a check definition, as PostgreSQL normalises it."""
    return [int(n) for n in re.findall(r"\d+", definition)]


async def test_given_the_v2_limits_when_a_category_at_each_limit_is_inserted_then_postgresql_accepts_it(
    cat_owner: asyncpg.Connection,
) -> None:
    await _add(cat_owner, 1, "n" * 215, "d" * 1500, 99)

    assert await cat_owner.fetchval("select count(*) from categories.category") == 1


@pytest.mark.parametrize(
    ("name", "description", "position", "constraint"),
    [
        ("n" * 216, "d", 0, "ck_category_name_length"),
        ("", "d", 0, "ck_category_name_length"),
        ("n", "d" * 1501, 0, "ck_category_description_length"),
        ("n", "d", 100, "ck_category_position"),
        ("n", "d", -1, "ck_category_position"),
    ],
)
async def test_given_the_v2_limits_when_a_category_beyond_a_limit_is_inserted_then_a_check_refuses_it(
    cat_owner: asyncpg.Connection, name: str, description: str, position: int, constraint: str
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match=constraint):
        await _add(cat_owner, 1, name, description, position)


async def test_given_v1_rows_when_the_chain_runs_to_head_twice_then_the_rows_are_unchanged(database_url: str) -> None:
    await _up(database_url, PREVIOUS)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await _add(connection, 1, "Receipts", "bills", 49)
        before = await connection.fetch("select * from categories.category")

        await _up(database_url, "0023")
        await _up(database_url, "0023")

        assert await connection.fetch("select * from categories.category") == before
    finally:
        await connection.close()


async def test_given_rows_within_the_v1_limits_when_downgraded_then_the_v1_checks_are_back_and_up_again_v2(
    database_url: str,
) -> None:
    await _up(database_url, "0023")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await _add(connection, 1, "n" * 40, "d" * 500, 49)

        await _down(database_url, PREVIOUS)
        v1 = await _definitions(connection)
        assert _numbers(v1["ck_category_name_length"]) == [1, 40]
        assert _numbers(v1["ck_category_description_length"]) == [500]
        assert _numbers(v1["ck_category_position"]) == [0, 49]
        with pytest.raises(asyncpg.CheckViolationError):
            await _add(connection, 2, "n" * 41)

        await _up(database_url, "0023")
        v2 = await _definitions(connection)
        assert _numbers(v2["ck_category_name_length"]) == [1, 215]
        assert _numbers(v2["ck_category_description_length"]) == [1500]
        assert _numbers(v2["ck_category_position"]) == [0, 99]
    finally:
        await connection.close()


@pytest.mark.parametrize(
    ("name", "description", "position"),
    [("n" * 41, "d", 0), ("n", "d" * 501, 0), ("n", "d", 50)],
)
async def test_given_a_row_beyond_the_v1_limits_when_downgraded_then_it_stops_with_a_clear_error_and_changes_nothing(
    database_url: str, name: str, description: str, position: int
) -> None:
    await _up(database_url, "0023")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await _add(connection, 1, name, description, position)
        before = await _definitions(connection)

        with pytest.raises(RuntimeError, match="v2 limits"):
            await _down(database_url, PREVIOUS)

        assert await _definitions(connection) == before
        assert await connection.fetchval("select version_num from alembic_version") == "0023"
        assert await connection.fetchval("select count(*) from categories.category") == 1
    finally:
        await connection.close()


async def test_given_the_head_when_compared_with_the_models_then_the_category_checks_do_not_drift(
    database_url: str,
) -> None:
    await _up(database_url, "head")

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"include_schemas": True}), Base.metadata
                )
            )
        model_checks = {
            c.name: str(c.sqltext)
            for c in Base.metadata.tables["categories.category"].constraints
            if isinstance(c, CheckConstraint)
        }
    finally:
        await engine.dispose()

    assert differences == []
    assert model_checks["ck_category_name_length"] == "char_length(name) BETWEEN 1 AND 215"
    assert model_checks["ck_category_description_length"] == "char_length(description) <= 1500"
    assert model_checks["ck_category_position"] == "position BETWEEN 0 AND 99"
