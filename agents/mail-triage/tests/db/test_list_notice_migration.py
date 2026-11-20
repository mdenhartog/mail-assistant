"""U-mail-categories-23, criterion 5: migration 0017 adds the list notice cursor to ``poll_state``.

The cursor is not the ``list_cursor`` of the label sync: that one says which versions Gmail has seen, this one which
versions Marco was told about. The agent's existing table-wide rights on ``poll_state`` cover the new column.
"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from alembic import command

from tests.db.conftest import alembic_config, plain_url

_COLUMNS = "select column_name from information_schema.columns where table_name = 'poll_state'"


async def _fetch(url: str, sql: str) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(plain_url(url))
    try:
        return await connection.fetch(sql)
    finally:
        await connection.close()


async def _execute(url: str, sql: str) -> None:
    connection = await asyncpg.connect(plain_url(url))
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


async def _columns(url: str) -> set[str]:
    return {r["column_name"] for r in await _fetch(url, _COLUMNS)}


async def test_given_0017_when_run_up_down_and_up_then_the_cursor_column_comes_goes_and_comes_back(
    database_url: str,
) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "0016")
    assert "list_notice_version" not in await _columns(database_url)
    await _execute(database_url, "insert into poll_state (id, history_id, web_notice_version) values (1, '5', 3)")

    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "0017")

    assert "list_notice_version" in await _columns(database_url)
    row = (await _fetch(database_url, "select * from poll_state"))[0]
    assert (row["history_id"], row["web_notice_version"], row["list_notice_version"]) == ("5", 3, None)

    await asyncio.to_thread(command.downgrade, alembic_config(database_url), "0016")

    assert "list_notice_version" not in await _columns(database_url)
    row = (await _fetch(database_url, "select * from poll_state"))[0]
    assert (row["history_id"], row["web_notice_version"]) == ("5", 3)  # the other cursors are untouched

    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "0017")

    assert "list_notice_version" in await _columns(database_url)


async def test_given_the_cursor_column_then_the_agent_moves_it_and_the_web_role_cannot_touch_poll_state(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await cat_agent.execute("insert into poll_state (id, history_id) values (1, '1')")
    await cat_agent.execute("update poll_state set list_notice_version = 4")

    assert await cat_owner.fetchval("select list_notice_version from poll_state") == 4
    for statement in ("update poll_state set list_notice_version = 9", "select list_notice_version from poll_state"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await cat_api.execute(statement)
    for statement in ("delete from poll_state", "truncate poll_state"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await cat_agent.execute(statement)
