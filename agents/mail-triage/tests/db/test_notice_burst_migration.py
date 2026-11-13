"""U-web-settings-56: migration 0011 gives every Undo token record a burst id and the first version of its burst."""

from __future__ import annotations

import asyncio

import asyncpg
from alembic import command

from tests.db.conftest import alembic_config

_INSERT = (
    "insert into web_notice_token (token, version, before, created_at, expires_at) "
    "values ('{token}', {version}, '{before}', now(), now() + interval '1 day')"
)


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _migrate(url: str, revision: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), revision)


async def _downgrade(url: str, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(url), revision)


async def _fetch(url: str, sql: str) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(_plain(url))
    try:
        return await connection.fetch(sql)
    finally:
        await connection.close()


async def _execute(url: str, sql: str) -> None:
    connection = await asyncpg.connect(_plain(url))
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


async def _columns(url: str) -> set[str]:
    rows = await _fetch(url, "select column_name from information_schema.columns where table_name='web_notice_token'")
    return {r["column_name"] for r in rows}


async def test_given_0011_when_run_up_down_and_up_then_the_columns_come_go_and_come_back_with_old_rows_grouped(
    database_url: str,
) -> None:
    await _migrate(database_url, "0008")
    assert "burst_id" not in await _columns(database_url)
    for token, version, before in (("a", 3, '{"quiet_start": 1}'), ("b", 4, '{"quiet_start": 1}'), ("c", 9, "{}")):
        await _execute(database_url, _INSERT.format(token=token, version=version, before=before))

    await _migrate(database_url, "0011")

    assert {"burst_id", "first_version"} <= await _columns(database_url)
    rows = {r["token"]: r for r in await _fetch(database_url, "select * from web_notice_token")}
    assert rows["a"]["burst_id"] == rows["b"]["burst_id"] != rows["c"]["burst_id"]  # old rows keep their grouping
    assert (rows["a"]["first_version"], rows["b"]["first_version"], rows["c"]["first_version"]) == (3, 3, 9)

    await _downgrade(database_url, "0008")

    assert "burst_id" not in await _columns(database_url)
    assert "first_version" not in await _columns(database_url)
    assert len(await _fetch(database_url, "select 1 from web_notice_token")) == 3

    await _migrate(database_url, "0011")

    assert {"burst_id", "first_version"} <= await _columns(database_url)
    assert len(await _fetch(database_url, "select 1 from web_notice_token")) == 3
