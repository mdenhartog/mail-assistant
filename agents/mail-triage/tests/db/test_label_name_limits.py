"""U-label-prefix-removal-21: the database limits of a label name follow the policy, 255 characters (not bytes)."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import re

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.db.conftest import alembic_config, insert_list, plain_url, write_list

LIMIT = 255
# table -> constraint -> the column it bounds
CONSTRAINTS = {
    "category": {"ck_category_name_length": "name"},
    "list_settings": {
        "ck_list_settings_archive_label": "archive_label",
        "ck_list_settings_other_label": "other_label",
    },
    "managed_label": {"ck_managed_label_name_length": "label_name"},
    "label_rename_item": {
        "ck_label_rename_item_old_name_length": "old_name",
        "ck_label_rename_item_new_name_length": "new_name",
    },
    "deleted_label": {"ck_deleted_label_name_length": "name"},
}
MULTIBYTE = ("é", "日", "😀")  # 2, 3 and 4 bytes in UTF-8


def _numbers(definition: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", definition)]


async def _definitions(connection: asyncpg.Connection, table: str) -> dict[str, str]:
    rows = await connection.fetch(
        "select conname, pg_get_constraintdef(oid) as d from pg_constraint "
        "where conrelid = $1::regclass and contype = 'c'",
        f"categories.{table}",
    )
    return {r["conname"]: r["d"] for r in rows}


async def _all_limits(connection: asyncpg.Connection) -> dict[str, str]:
    found: dict[str, str] = {}
    for table, constraints in CONSTRAINTS.items():
        if not await connection.fetchval("select to_regclass($1) is not null", f"categories.{table}"):
            continue
        definitions = await _definitions(connection, table)
        found.update({name: definitions[name] for name in constraints if name in definitions})
    return found


async def _store(connection: asyncpg.Connection, table: str, column: str, value: str) -> None:
    """Store ``value`` in ``column`` of ``table`` in a transaction that is rolled back by the caller's savepoint."""
    if table == "category":
        await write_list(connection, "mb1", 1, [value])
    elif table == "list_settings":
        async with connection.transaction():
            await connection.execute("insert into categories.list_version (mailbox_id, version) values ('mb1', 1)")
            await connection.execute(
                f"insert into categories.list_settings (mailbox_id, version, {column}) values ('mb1', 1, $1)",  # noqa: S608
                value,
            )
    elif table == "managed_label":
        await connection.execute(
            "insert into categories.managed_label (mailbox_id, label_id, role, label_name) "
            "values ('mb1', 'Label_1', 'other', $1)",
            value,
        )
    elif table == "label_rename_item":
        old, new = ("$1", "'new'") if column == "old_name" else ("'old'", "$1")
        await connection.execute(
            "insert into categories.label_rename_item (mailbox_id, label_id, old_name, new_name, action) "  # noqa: S608
            f"values ('mb1', 'Label_1', {old}, {new}, 'rename')",
            value,
        )
    else:
        await connection.execute(
            "insert into categories.deleted_label (mailbox_id, label_id_hash, name) "
            "values ('mb1', repeat('a', 64), $1)",
            value,
        )


CASES = [(table, constraint, column) for table, cs in CONSTRAINTS.items() for constraint, column in cs.items()]


@pytest.mark.parametrize(("table", "constraint", "column"), CASES)
async def test_given_a_name_of_255_characters_when_stored_then_it_is_accepted_in_every_label_table(
    cat_owner: asyncpg.Connection, table: str, constraint: str, column: str
) -> None:
    await _store(cat_owner, table, column, "n" * LIMIT)

    assert await cat_owner.fetchval(f"select count(*) from categories.{table}") == 1  # noqa: S608


@pytest.mark.parametrize(("table", "constraint", "column"), CASES)
async def test_given_a_name_of_256_characters_when_stored_then_the_named_check_refuses_it(
    cat_owner: asyncpg.Connection, table: str, constraint: str, column: str
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match=constraint):
        await _store(cat_owner, table, column, "n" * (LIMIT + 1))


@pytest.mark.parametrize("char", MULTIBYTE)
@pytest.mark.parametrize(("table", "constraint", "column"), CASES)
async def test_given_a_multibyte_name_of_255_characters_when_stored_then_it_is_accepted_and_256_refused(
    cat_owner: asyncpg.Connection, table: str, constraint: str, column: str, char: str
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match=constraint):
        await _store(cat_owner, table, column, char * (LIMIT + 1))

    await _store(cat_owner, table, column, char * LIMIT)  # more than 255 bytes, 255 characters

    assert await cat_owner.fetchval(f"select count(*) from categories.{table}") == 1  # noqa: S608


async def test_given_the_api_role_when_it_saves_a_list_with_a_255_character_name_then_the_database_accepts_it(
    cat_api: asyncpg.Connection,
) -> None:
    name = "é" * LIMIT
    async with cat_api.transaction():
        await insert_list(cat_api, "mb1", 1, [name])
        await cat_api.execute(
            "insert into categories.list_settings (mailbox_id, version, archive_label, other_label) "
            "values ('mb1', 1, $1, $1)",
            name,
        )

    assert await cat_api.fetchval("select name from categories.category where mailbox_id = 'mb1'") == name


async def test_given_the_head_when_compared_with_the_models_then_the_checks_are_255_and_do_not_drift(
    database_url: str,
) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "head")
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"include_schemas": True}), Base.metadata
                )
            )
    finally:
        await engine.dispose()

    assert differences == []
    for table, constraints in CONSTRAINTS.items():
        model = {
            c.name: str(c.sqltext)
            for c in Base.metadata.tables[f"categories.{table}"].constraints
            if isinstance(c, CheckConstraint)
        }
        for name in constraints:
            assert _numbers(model[name]) == ([1, LIMIT] if table in ("category", "list_settings") else [LIMIT]), name


async def test_given_0030_ran_when_it_runs_again_then_the_limits_are_the_same_and_the_data_is_kept(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0030")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await connection.execute("insert into categories.mailbox (id) values ('mb1')")
        await write_list(connection, "mb1", 1, ["n" * LIMIT])
        before = await _all_limits(connection)
        assert len(before) == len(CASES)
        assert all(LIMIT in _numbers(d) for d in before.values())
        rows = await connection.fetch("select * from categories.category")

        await asyncio.to_thread(command.stamp, config, "0029")
        await asyncio.to_thread(command.upgrade, config, "0030")

        assert await _all_limits(connection) == before
        assert await connection.fetch("select * from categories.category") == rows
    finally:
        await connection.close()


async def test_given_0030_when_downgraded_then_the_old_limits_are_back_and_nothing_else_changes(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0029")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        old = await _all_limits(connection)
        assert {k: _numbers(v) for k, v in old.items()} == {
            "ck_category_name_length": [1, 215],
            "ck_list_settings_archive_label": [1, 225],
        }
        await asyncio.to_thread(command.upgrade, config, "0030")

        await asyncio.to_thread(command.downgrade, config, "0029")

        assert await _all_limits(connection) == old
        for table in ("category", "list_settings"):
            names = set(await _definitions(connection, table))
            assert names >= set(CONSTRAINTS[table]) - {"ck_list_settings_other_label"}
        assert "ck_list_settings_other_label" not in await _definitions(connection, "list_settings")
    finally:
        await connection.close()
