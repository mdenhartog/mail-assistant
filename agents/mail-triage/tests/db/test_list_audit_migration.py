"""U-label-structure-14: revision 0028, the list audit records kind, tick, senders and the general instructions."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING

import asyncpg
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base
from tests.db.conftest import alembic_config, plain_url

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

_FUNCTION = "categories.list_json(text, integer)"
_AUDIT_COLUMNS = {"old_instructions", "new_instructions"}


async def _columns(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch(
        "select column_name from information_schema.columns where table_schema = 'categories' "
        "and table_name = 'list_audit'"
    )
    return {r["column_name"] for r in rows}


async def test_given_0028_when_upgraded_downgraded_and_upgraded_again_then_function_and_columns_follow_and_no_drift(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0027")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        before = await connection.fetchval(f"select pg_get_functiondef('{_FUNCTION}'::regprocedure)")
        assert not _AUDIT_COLUMNS & await _columns(connection)

        await asyncio.to_thread(command.upgrade, config, "0028")
        after = await connection.fetchval(f"select pg_get_functiondef('{_FUNCTION}'::regprocedure)")
        assert "senders" in after
        assert await _columns(connection) >= _AUDIT_COLUMNS

        await asyncio.to_thread(command.downgrade, config, "0027")
        assert await connection.fetchval(f"select pg_get_functiondef('{_FUNCTION}'::regprocedure)") == before
        assert not _AUDIT_COLUMNS & await _columns(connection)

        await asyncio.to_thread(command.upgrade, config, "0028")
        assert await _columns(connection) >= _AUDIT_COLUMNS
    finally:
        await connection.close()

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:

            def diff(sync: Connection) -> list[object]:
                context = MigrationContext.configure(sync, opts={"include_schemas": True})
                return [d for d in compare_metadata(context, Base.metadata) if "list_audit" in str(d)]

            assert await conn.run_sync(diff) == []
    finally:
        await engine.dispose()


async def test_given_old_audit_rows_when_0028_runs_then_they_stay_and_read_as_no_instructions(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0027")
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await connection.execute("insert into categories.mailbox (id) values ('mb1')")
        await connection.execute(
            "insert into categories.list_audit (mailbox_id, version, old_list, new_list, channel, actor_digest) "
            "values ('mb1', 1, '[]', '[]', 'web', repeat('a', 64))"
        )
        await asyncio.to_thread(command.upgrade, config, "0028")
        row = await connection.fetchrow("select old_instructions, new_instructions from categories.list_audit")
        assert row is not None
        assert (row["old_instructions"], row["new_instructions"]) == ("", "")
    finally:
        await connection.close()


async def _write(  # noqa: PLR0913
    connection: asyncpg.Connection,
    version: int,
    *,
    kind: str,
    notify: bool,
    senders: list[str],
    instructions: str,
) -> None:
    async with connection.transaction():
        await connection.execute(
            "insert into categories.list_version (mailbox_id, version) values ('mb1', $1)", version
        )
        identity = uuid.UUID(int=7)
        if version == 1:
            await connection.execute(
                "insert into categories.category_identity (mailbox_id, id) values ('mb1', $1)", identity
            )
        await connection.execute(
            "insert into categories.category (mailbox_id, version, id, name, description, position, kind, notify) "
            "values ('mb1', $1, $2, 'Bills', 'Invoices', 0, $3, $4)",
            version,
            identity,
            kind,
            notify,
        )
        for entry in senders:
            await connection.execute(
                "insert into categories.category_sender (mailbox_id, version, category_id, entry, is_domain) "
                "values ('mb1', $1, $2, $3, false)",
                version,
                identity,
                entry,
            )
        await connection.execute(
            "insert into categories.list_settings (mailbox_id, version, general_instructions, archive_label) "
            "values ('mb1', $1, $2, 'Assistant/Archive')",
            version,
            instructions,
        )


async def test_given_a_tick_a_sender_or_an_instruction_changes_when_confirmed_then_the_audit_shows_the_change(
    cat_owner: asyncpg.Connection,
) -> None:
    await _write(cat_owner, 1, kind="topic", notify=False, senders=[], instructions="")
    await _write(
        cat_owner, 2, kind="extra", notify=True, senders=["b@example.nl", "a@example.nl"], instructions="Be brief"
    )

    rows = await cat_owner.fetch(
        "select version, old_list, new_list, old_instructions, new_instructions from categories.list_audit order by 1"
    )
    first_new = json.loads(rows[0]["new_list"])[0]
    second_old, second_new = json.loads(rows[1]["old_list"])[0], json.loads(rows[1]["new_list"])[0]
    assert (first_new["kind"], first_new["notify"], first_new["senders"]) == ("topic", False, [])
    assert second_old == first_new
    assert (second_new["kind"], second_new["notify"]) == ("extra", True)
    assert second_new["senders"] == [
        {"entry": "a@example.nl", "is_domain": False, "subdomains": False},
        {"entry": "b@example.nl", "is_domain": False, "subdomains": False},
    ]  # in a fixed order, so the same list always reads the same
    assert (second_new["name"], second_new["description"]) == ("Bills", "Invoices")  # what the notice reads is kept
    assert [(r["old_instructions"], r["new_instructions"]) for r in rows] == [("", ""), ("", "Be brief")]


async def test_given_a_version_without_a_settings_row_when_audited_then_the_instructions_read_as_empty(
    cat_agent: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    async with cat_agent.transaction():
        await cat_agent.execute("insert into categories.list_version (mailbox_id, version) values ('mb1', 1)")

    row = await cat_owner.fetchrow("select new_list, new_instructions from categories.list_audit")
    assert row is not None
    assert (json.loads(row["new_list"]), row["new_instructions"]) == ([], "")
