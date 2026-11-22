"""U-mail-categories-03, criterion 2 (AC-20): the rights of the api and agent roles are exactly the design matrix.

The matrix below is written out by hand from the design ("Grants and functions"); a table, a column or an operation
that is not in it must be refused with SQLSTATE 42501 for each role.
"""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg
import pytest

from tests.db.conftest import AGENT_ROLE, API_ROLE

ALL = "*"
Columns = frozenset[str] | str  # a set of column names, or ALL
TABLES = (
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
    "category_sender",
    "list_settings",
    "upload_preview",
    "sender_skip",
)
OPERATIONS = ("select", "insert", "update", "delete", "truncate")


@dataclass(frozen=True)
class Rights:
    """What one role may do with one table: columns for select, insert and update, and whether it may delete."""

    select: Columns = frozenset()
    insert: Columns = frozenset()
    update: Columns = frozenset()
    delete: bool = False


@dataclass(frozen=True)
class Row:
    """One table of the matrix for both roles."""

    api: Rights = field(default_factory=Rights)
    agent: Rights = field(default_factory=Rights)


_REPLACED = Rights(select=ALL, insert=ALL, update=ALL, delete=True)  # derived and cursor tables: replaced each cycle
MATRIX: dict[str, Row] = {
    "mailbox": Row(api=Rights(select=ALL), agent=Rights(select=ALL, insert=ALL)),
    "category_identity": Row(
        api=Rights(select=ALL, insert=frozenset({"mailbox_id", "id"})),
        agent=Rights(select=ALL, insert=frozenset({"mailbox_id", "id"})),
    ),
    "list_version": Row(
        api=Rights(select=ALL, insert=frozenset({"mailbox_id", "version"})),
        agent=Rights(select=ALL, insert=frozenset({"mailbox_id", "version"})),
    ),
    "category": Row(api=Rights(select=ALL, insert=ALL), agent=Rights(select=ALL, insert=ALL)),
    "list_audit": Row(agent=Rights(select=ALL)),
    "category_count": Row(api=Rights(select=ALL), agent=_REPLACED),
    "gmail_label": Row(api=Rights(select=ALL), agent=_REPLACED),
    "category_label": Row(agent=_REPLACED),
    "filing": Row(
        agent=Rights(
            select=ALL,
            insert=frozenset(
                {
                    "mailbox_id",
                    "message_id",
                    "list_version",
                    "topic_id",
                    "extra_id",
                    "source",
                    "source_ref",
                }
            ),
        )
    ),
    "list_cursor": Row(agent=_REPLACED),
    "rejection": Row(agent=Rights(select=ALL, insert=frozenset({"mailbox_id", "message_id", "list_version"}))),
    "telegram_action": Row(
        agent=Rights(
            select=ALL,
            insert=frozenset({"mailbox_id", "nonce_hash", "chat_id", "kind", "target", "expires_at"}),
            update=frozenset({"used_at"}),
        )
    ),
    "apply_config": Row(api=Rights(select=ALL), agent=Rights(select=ALL, insert=ALL, update=ALL)),
    # INT-008 (U-label-structure-05): insert-only like category; the preview belongs to the api alone (ADR-0058).
    "category_sender": Row(api=Rights(select=ALL, insert=ALL), agent=Rights(select=ALL, insert=ALL)),
    "list_settings": Row(api=Rights(select=ALL, insert=ALL), agent=Rights(select=ALL, insert=ALL)),
    "upload_preview": Row(
        api=Rights(
            select=ALL,
            insert=frozenset(
                {"mailbox_id", "id", "session_digest", "file_hash", "base_version", "content", "expires_at"}
            ),
            update=frozenset({"used_at"}),
        )
    ),
    # INT-008 (U-label-structure-36): the agent counts, the api reads (the count of an entry on the lists page).
    "sender_skip": Row(api=Rights(select=ALL), agent=_REPLACED),
}
ROLES = {"api": API_ROLE, "agent": AGENT_ROLE}


def _columns(rights: Rights, operation: str, every_column: list[str]) -> frozenset[str]:
    """The columns of a table that ``operation`` is allowed on."""
    allowed = getattr(rights, operation)
    return frozenset(every_column) if allowed == ALL else allowed


def _statement(operation: str, table: str, column: str) -> str:
    target = f"categories.{table}"
    return {
        "select": f"select {column} from {target} limit 0",
        "insert": f"insert into {target} ({column}) values (default)",
        "update": f"update {target} set {column} = {column} where false",
        "delete": f"delete from {target} where false",
        "truncate": f"truncate {target}",
    }[operation]


async def _every_column(owner: asyncpg.Connection, table: str) -> list[str]:
    rows = await owner.fetch(
        "select column_name from information_schema.columns where table_schema = 'categories' and table_name = $1 "
        "order by ordinal_position",
        table,
    )
    return [r["column_name"] for r in rows]


async def _sqlstate(connection: asyncpg.Connection, statement: str) -> str | None:
    try:
        await connection.execute(statement)
    except asyncpg.PostgresError as error:
        return str(error.sqlstate)  # pyright: ignore[reportAttributeAccessIssue]  # asyncpg types it on subclasses
    return None


def test_given_the_matrix_when_its_tables_are_compared_with_the_list_then_none_is_missing() -> None:
    assert set(MATRIX) == set(TABLES)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("table", TABLES)
async def test_given_the_matrix_when_a_role_runs_a_statement_then_the_unlisted_ones_get_42501(  # noqa: PLR0913, PLR0917
    cat_owner: asyncpg.Connection,
    cat_api: asyncpg.Connection,
    cat_agent: asyncpg.Connection,
    table: str,
    role: str,
    operation: str,
) -> None:
    connection = cat_api if role == "api" else cat_agent
    rights: Rights = getattr(MATRIX[table], role)
    every_column = await _every_column(cat_owner, table)
    if operation in ("delete", "truncate"):
        allowed = operation == "delete" and rights.delete
        assert await _sqlstate(connection, _statement(operation, table, "")) == (None if allowed else "42501")
        return
    allowed_columns = _columns(rights, operation, every_column)
    for column in every_column:
        state = await _sqlstate(connection, _statement(operation, table, column))
        if column in allowed_columns and operation == "select":
            assert state is None, (table, role, operation, column)
        elif column not in allowed_columns:
            assert state == "42501", (table, role, operation, column, state)
        # an allowed insert or update is not run: its only failures are constraints, which are not under test here


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("table", TABLES)
async def test_given_the_matrix_when_the_catalog_is_asked_then_every_column_privilege_is_exactly_the_listed_one(
    cat_owner: asyncpg.Connection, table: str, role: str
) -> None:
    rights: Rights = getattr(MATRIX[table], role)
    every_column = await _every_column(cat_owner, table)
    target = f"categories.{table}"
    for operation in ("select", "insert", "update"):
        expected = _columns(rights, operation, every_column)
        for column in every_column:
            actual = await cat_owner.fetchval(
                "select has_column_privilege($1, $2, $3, $4)", ROLES[role], target, column, operation.upper()
            )
            assert actual == (column in expected), (table, role, operation, column)
    for privilege, expected_flag in (
        ("DELETE", rights.delete),
        ("TRUNCATE", False),
        ("REFERENCES", False),
        ("TRIGGER", False),
    ):
        actual = await cat_owner.fetchval("select has_table_privilege($1, $2, $3)", ROLES[role], target, privilege)
        assert actual == expected_flag, (table, role, privilege)


@pytest.mark.parametrize("role", ROLES.values())
async def test_given_the_runtime_roles_when_they_use_ddl_or_other_schema_objects_then_postgres_refuses_it(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, cat_agent: asyncpg.Connection, role: str
) -> None:
    connection = cat_api if role == API_ROLE else cat_agent

    for statement in (
        "create table categories.evil (id int)",
        "drop table categories.category",
        "alter table categories.category disable trigger all",
        "set session_replication_role = replica",
    ):
        assert await _sqlstate(connection, statement) == "42501", statement


async def test_given_the_functions_when_their_execute_rights_are_read_then_only_the_planned_roles_have_them(
    cat_owner: asyncpg.Connection,
) -> None:
    async def can(role: str, function: str) -> bool:
        return bool(await cat_owner.fetchval("select has_function_privilege($1, $2, 'EXECUTE')", role, function))

    assert not await can("public", "categories.purge_expired()")
    assert await can(AGENT_ROLE, "categories.purge_expired()")
    assert not await can(API_ROLE, "categories.purge_expired()")
    assert await can(API_ROLE, "categories.contract_version()")
    assert await can(AGENT_ROLE, "categories.contract_version()")
    assert not await can("public", "categories.contract_version()")


async def test_given_the_api_role_when_it_selects_a_token_table_in_another_schema_then_postgres_refuses_it(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await cat_owner.execute("create schema other_system")
    await cat_owner.execute("create table other_system.token (id int primary key, secret text)")
    await cat_owner.execute("insert into other_system.token values (1, 'test-seeded-token')")
    await cat_owner.execute("insert into oauth_token (id, ciphertext, updated_at) values (1, '\\x01', now())")

    assert await _sqlstate(cat_api, "select * from other_system.token") == "42501"
    assert await _sqlstate(cat_api, "select secret from other_system.token") == "42501"
    assert await _sqlstate(cat_api, "select * from public.oauth_token") == "42501"
    assert await _sqlstate(cat_api, "select * from settings.settings_change") == "42501"
    assert await _sqlstate(cat_api, "select * from web_auth.web_lock") is None  # the one table its web role may read
