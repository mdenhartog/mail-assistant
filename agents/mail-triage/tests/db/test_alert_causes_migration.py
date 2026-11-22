"""U-label-structure-10: revision 0026 adds the alert causes and the verified domain, and takes them off again."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio

import asyncpg
from alembic import command

from tests.db.conftest import alembic_config, plain_url


async def _columns(connection: asyncpg.Connection, table: str) -> set[str]:
    rows = await connection.fetch(
        "select column_name from information_schema.columns where table_schema = 'public' and table_name = $1", table
    )
    return {r["column_name"] for r in rows}


async def test_given_0026_when_it_runs_up_and_down_then_the_columns_come_and_go_and_alerts_stay(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0025")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await connection.execute(
            "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) values ('m1', 't1', true, now())"
        )
        await connection.execute(
            "insert into alert (mail_item_id, state, created_at, updated_at) "
            "select id, 'open', now(), now() from mail_item"
        )
        await asyncio.to_thread(command.upgrade, config, "0026")
        assert {"causes", "by_rule"} <= await _columns(connection, "alert")
        assert "verified_domain" in await _columns(connection, "mail_item")
        row = await connection.fetchrow("select causes, by_rule from alert")
        assert row is not None
        assert (row["causes"], row["by_rule"]) == (None, False)  # an alert from before reads as urgent

        await asyncio.to_thread(command.downgrade, config, "0025")
        assert not {"causes", "by_rule"} & await _columns(connection, "alert")
        assert "verified_domain" not in await _columns(connection, "mail_item")
        assert await connection.fetchval("select count(*) from alert") == 1
    finally:
        await connection.close()
