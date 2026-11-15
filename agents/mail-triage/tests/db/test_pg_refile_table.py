"""U-mail-categories-25, criterion 4 (ADR-0043, ADR-0047, ADR-0030): the report table of the daily re-file report.

Migration 0019 adds ``categories.refile_report`` (counts only, ``mailbox_id`` first in every key), the SECURITY DEFINER
function ``record_refile_report`` that is the agent's only way to write it, and the retention in ``purge_expired()``.
Neither the api nor the agent role can read or write the table itself.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic import command

from tests.db.conftest import AGENT_ROLE, API_ROLE, alembic_config, plain_url

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

TABLE = "categories.refile_report"
FUNCTION = "categories.record_refile_report(text, integer, integer, integer, integer, integer)"
_RECORD = "select categories.record_refile_report($1, $2, $3, $4, $5, $6)"


async def _purge(connection: asyncpg.Connection) -> dict[str, int]:
    return json.loads(str(await connection.fetchval("select categories.purge_expired()")))


async def _record(connection: asyncpg.Connection, mailbox: str = "mb1", *counts: int) -> None:
    filed, checked, refiled, in_other, gone = counts or (10, 10, 1, 2, 0)
    await connection.execute(_RECORD, mailbox, filed, checked, refiled, in_other, gone)


async def test_given_0019_when_run_up_down_and_up_then_the_table_and_function_come_go_and_come_back(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0018")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        assert await connection.fetchval("select to_regclass($1)", TABLE) is None

        await asyncio.to_thread(command.upgrade, config, "0019")

        assert await connection.fetchval("select to_regclass($1)", TABLE) is not None
        assert await connection.fetchval("select to_regprocedure($1)", FUNCTION) is not None
        assert "refile_report" in await connection.fetchval(
            "select pg_get_functiondef('categories.purge_expired()'::regprocedure)"
        )

        await asyncio.to_thread(command.downgrade, config, "0018")

        assert await connection.fetchval("select to_regclass($1)", TABLE) is None
        assert await connection.fetchval("select to_regprocedure($1)", FUNCTION) is None
        assert "refile_report" not in await connection.fetchval(
            "select pg_get_functiondef('categories.purge_expired()'::regprocedure)"
        )

        await asyncio.to_thread(command.upgrade, config, "0019")

        assert await connection.fetchval("select to_regclass($1)", TABLE) is not None
    finally:
        await connection.close()


async def test_given_the_table_then_the_mailbox_id_comes_first_in_every_key_and_it_holds_counts_only(
    cat_owner: asyncpg.Connection,
) -> None:
    keys = await cat_owner.fetch(
        "select c.conname, a.attname from pg_constraint c "
        "join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1] "
        "where c.conrelid = $1::regclass and c.contype in ('p', 'u')",
        TABLE,
    )
    indexes = await cat_owner.fetch(
        "select a.attname from pg_index i join pg_attribute a on a.attrelid = i.indrelid and a.attnum = i.indkey[0] "
        "where i.indrelid = $1::regclass",
        TABLE,
    )
    columns = {
        r["column_name"]
        for r in await cat_owner.fetch(
            "select column_name from information_schema.columns where table_schema = 'categories' "
            "and table_name = 'refile_report'"
        )
    }

    assert keys
    assert {r["attname"] for r in keys} == {"mailbox_id"}
    assert {r["attname"] for r in indexes} == {"mailbox_id"}
    assert columns == {"mailbox_id", "id", "at", "filed", "checked", "refiled", "in_other", "gone"}


@pytest.mark.parametrize("role", [API_ROLE, AGENT_ROLE])
@pytest.mark.parametrize("right", ["select", "insert", "update", "delete", "truncate", "references", "trigger"])
async def test_given_a_runtime_role_then_it_has_no_right_on_the_report_table(
    cat_owner: asyncpg.Connection, role: str, right: str
) -> None:
    assert not await cat_owner.fetchval("select has_table_privilege($1, $2, $3)", role, TABLE, right)
    if right in {"select", "insert", "update", "references"}:  # column rights exist for these only
        assert not await cat_owner.fetchval("select has_any_column_privilege($1, $2, $3)", role, TABLE, right)


async def test_given_the_agent_when_it_reads_or_writes_the_table_directly_then_postgres_refuses_with_42501(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    attempts: list[Callable[[], Awaitable[object]]] = [
        lambda: cat_agent.fetch(f"select * from {TABLE}"),
        lambda: cat_agent.execute(
            f"insert into {TABLE} (mailbox_id, filed, checked, refiled, in_other, gone) values ('mb1', 1, 1, 0, 0, 0)"
        ),
        lambda: cat_agent.execute(f"update {TABLE} set filed = 0"),
        lambda: cat_agent.execute(f"delete from {TABLE}"),
    ]
    for attempt in attempts:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await attempt()
    assert await cat_owner.fetchval(f"select count(*) from {TABLE}") == 0


async def test_given_the_function_then_only_the_agent_may_run_it_and_the_definer_owns_it(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    assert await cat_owner.fetchval("select has_function_privilege($1, $2, 'EXECUTE')", AGENT_ROLE, FUNCTION)
    assert not await cat_owner.fetchval("select has_function_privilege($1, $2, 'EXECUTE')", API_ROLE, FUNCTION)
    assert not await cat_owner.fetchval(
        "select has_function_privilege('public', $1, 'EXECUTE')", FUNCTION
    )  # nobody else, by way of PUBLIC
    owner = await cat_owner.fetchval("select proowner::regrole::text from pg_proc where oid = $1::regprocedure", FUNCTION)
    assert owner == "categories_definer"
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _record(cat_api)


async def test_given_the_agent_when_it_records_a_report_then_the_row_has_the_counts_and_the_database_time(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _record(cat_agent, "mb1", 12, 10, 3, 4, 1)

    row = await cat_owner.fetchrow(f"select *, at = now() as db_clock from {TABLE}")  # noqa: S608

    assert row is not None
    assert (row["mailbox_id"], row["filed"], row["checked"], row["refiled"], row["in_other"], row["gone"]) == (
        "mb1",
        12,
        10,
        3,
        4,
        1,
    )
    assert row["at"] is not None


@pytest.mark.parametrize(
    "counts",
    [(-1, 0, 0, 0, 0), (5, 6, 0, 0, 0), (5, 5, 6, 0, 0), (5, 5, 0, 6, 0), (5, 5, 0, 0, 6)],
    ids=["negative", "checked>filed", "refiled>checked", "other>checked", "gone>checked"],
)
async def test_given_impossible_counts_then_the_row_is_refused(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, counts: tuple[int, ...]
) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        await _record(cat_agent, "mb1", *counts)
    assert await cat_owner.fetchval(f"select count(*) from {TABLE}") == 0


async def test_given_an_unknown_mailbox_then_the_row_is_refused_by_the_foreign_key(
    cat_agent: asyncpg.Connection,
) -> None:
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await _record(cat_agent, "nobody")


async def test_given_old_and_young_reports_when_the_purge_runs_then_rows_past_a_year_go_and_the_rest_stay(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    for mailbox in ("mb1", "mb2"):
        await _record(cat_agent, mailbox)
        await _record(cat_agent, mailbox)
    ids = [r["id"] for r in await cat_owner.fetch(f"select id from {TABLE} order by mailbox_id, id")]  # noqa: S608
    await cat_owner.execute(f"update {TABLE} set at = now() - interval '400 days' where id = any($1::bigint[])", ids[::2])
    await cat_owner.execute(f"update {TABLE} set at = now() - interval '300 days' where id = any($1::bigint[])", ids[1::2])

    counts = await _purge(cat_agent)

    assert counts["refile_report"] == 2
    left = await cat_owner.fetch(f"select mailbox_id from {TABLE} order by mailbox_id")  # noqa: S608
    assert [r["mailbox_id"] for r in left] == ["mb1", "mb2"]  # the young row of each mailbox survives


async def test_given_the_purge_when_the_agent_changes_its_session_then_a_young_report_still_survives(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _record(cat_agent)
    await cat_agent.execute("set time zone 'Pacific/Kiritimati'")
    await cat_agent.execute("set search_path = pg_temp")

    counts = await _purge(cat_agent)

    assert counts["refile_report"] == 0
    assert await cat_owner.fetchval(f"select count(*) from {TABLE}") == 1  # noqa: S608
