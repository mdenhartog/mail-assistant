"""U-mail-categories-03, criterion 1: the categories revision goes up and down and leaves the other schemas alone."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio

import asyncpg
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.db.conftest import alembic_config

PREVIOUS = "0013"
LIST_TABLES = {
    "mailbox",
    "category_identity",
    "list_version",
    "category",
    "list_audit",
    "category_count",
    "gmail_label",
    "category_label",
    "filing",
    "list_cursor",
    "rejection",
    "telegram_action",
    "apply_config",
}
PLAN_TABLES = {"plan", "plan_item", "plan_decision", "plan_approval", "apply_audit", "move_back_request"}  # 0015
REPORT_TABLES = {"refile_report"}  # 0019
CONTRACT_V2_TABLES = {"category_sender", "list_settings", "upload_preview"}  # 0024
SENDER_SKIP_TABLES = {"sender_skip"}  # 0027
RESORT_REQUEST_TABLES = {"resort_request"}  # 0029
LABEL_BOUNDARY_TABLES = {  # 0030
    "managed_label",
    "managed_label_released",
    "label_migration",
    "label_rename_item",
    "label_empty_since",
    "deleted_label",
    "label_confirmation",
    "label_restore_request",
}
ALL_TABLES = (
    LIST_TABLES
    | PLAN_TABLES
    | REPORT_TABLES
    | CONTRACT_V2_TABLES
    | SENDER_SKIP_TABLES
    | RESORT_REQUEST_TABLES
    | LABEL_BOUNDARY_TABLES
)


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _up(url: str, revision: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), revision)


async def _down(url: str, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(url), revision)


async def _fetch(url: str, sql: str) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(_plain(url))
    try:
        return await connection.fetch(sql)
    finally:
        await connection.close()


async def _tables(url: str) -> set[str]:
    rows = await _fetch(url, "select table_name from information_schema.tables where table_schema = 'categories'")
    return {r["table_name"] for r in rows}


_OTHER_DATA = (
    "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) values ('m1', 't1', false, now()); "
    "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, updated_by) "
    "values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'telegram', '42')"
)


async def test_given_data_in_other_schemas_when_the_revision_runs_up_and_down_then_only_categories_comes_and_goes(
    database_url: str,
) -> None:
    await _up(database_url, PREVIOUS)
    connection = await asyncpg.connect(_plain(database_url))
    try:
        await connection.execute(_OTHER_DATA)
    finally:
        await connection.close()
    assert await _tables(database_url) == set()

    await _up(database_url, "head")

    assert await _tables(database_url) == ALL_TABLES
    await _down(database_url, PREVIOUS)
    assert await _tables(database_url) == set()
    assert await _fetch(database_url, "select 1 from pg_namespace where nspname = 'categories'") == []
    assert len(await _fetch(database_url, "select 1 from mail_item")) == 1
    assert len(await _fetch(database_url, "select 1 from settings.schedule")) == 1
    assert len(await _fetch(database_url, "select 1 from settings.settings_change")) == 1
    await _up(database_url, "head")
    assert await _tables(database_url) == ALL_TABLES


async def test_given_the_head_when_compared_with_the_models_then_there_is_no_difference(database_url: str) -> None:
    await _up(database_url, "head")

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


async def test_given_every_categories_table_when_its_primary_key_is_read_then_the_mailbox_id_comes_first(
    migrated_url: str,
) -> None:
    rows = await _fetch(
        migrated_url,
        "select c.relname as t, (select a.attname from pg_attribute a where a.attrelid = c.oid "
        "and a.attnum = i.indkey[0]) as first_column "
        "from pg_index i join pg_class c on c.oid = i.indrelid join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'categories' and i.indisprimary",
    )

    assert {r["t"] for r in rows} == ALL_TABLES
    assert {r["t"]: r["first_column"] for r in rows if r["t"] != "mailbox"} == dict.fromkeys(
        ALL_TABLES - {"mailbox"}, "mailbox_id"
    )


async def test_given_the_head_when_the_contract_version_is_read_then_it_is_the_categories_one(
    migrated_url: str,
) -> None:
    rows = await _fetch(migrated_url, "select categories.contract_version() as v")

    assert rows[0]["v"] == 1
