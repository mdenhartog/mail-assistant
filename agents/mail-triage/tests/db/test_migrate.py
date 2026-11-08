"""The agent brings its own schema up to date when it starts (after it holds the single-replica lock)."""

from __future__ import annotations

import asyncpg

from app.db.migrate import upgrade


async def _tables(url: str) -> set[str]:
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        rows = await connection.fetch("select tablename from pg_tables where schemaname = 'public'")
    finally:
        await connection.close()
    return {row["tablename"] for row in rows}


async def test_given_an_empty_database_when_upgraded_then_all_tables_exist_and_a_second_run_changes_nothing(
    database_url: str,
) -> None:
    await upgrade(database_url)
    await upgrade(database_url)

    tables = await _tables(database_url)
    assert {"mail_item", "alert", "draft", "audit_log", "oauth_token", "poll_state", "overview_log"} <= tables
