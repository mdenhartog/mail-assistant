"""U-label-prefix-removal-02: revision 0030, managed labels, the rename plan, its state, timers, settings (ADR-0060/61).

Criteria 1 to 4 and 8 walk the revision on a database at 0029 (``database_url``); criteria 5 to 7 run on the migrated
template with the real roles (``SET SESSION AUTHORIZATION``).
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from alembic import command

from tests.db.conftest import alembic_config, plain_url
from tests.db.plan_support import sqlstate_of

NEW_TABLES = (
    "managed_label",
    "label_migration",
    "label_rename_item",
    "label_empty_since",
    "deleted_label",
    "label_confirmation",
    "label_restore_request",
)
CONFIRM = "select categories.confirm_label_rename($1, $2, $3::text[])"
RESTORE = "select categories.request_label_restore($1)"
BOUNDS = (
    ("label_wait_minutes", 4),
    ("label_wait_minutes", 721),
    ("label_protection_days", 0),
    ("label_protection_days", 31),
    ("label_retention_days", 6),
    ("label_retention_days", 91),
)


async def _at_0029(database_url: str) -> asyncpg.Connection:
    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "0029")
    return await asyncpg.connect(plain_url(database_url))


async def _seed(connection: asyncpg.Connection) -> dict[str, uuid.UUID]:
    """``mbA`` with two Assistant/ labels, ``mbB`` with a list label that has no prefix, ``mbC`` with nothing."""
    ids = {name: uuid.uuid4() for name in ("bills", "work", "plain")}
    await connection.execute("insert into categories.mailbox (id) values ('mbA'), ('mbB'), ('mbC')")
    for name, mailbox in (("bills", "mbA"), ("work", "mbA"), ("plain", "mbB")):
        await connection.execute(
            "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", mailbox, ids[name]
        )
    await connection.execute(
        "insert into categories.category_label (mailbox_id, category_id, label_id, label_name) values "
        "('mbA', $1, 'Label_1', 'Assistant/Bills'), ('mbA', $2, 'Label_2', 'Assistant/Work'), "
        "('mbB', $3, 'Label_3', 'Plain')",
        ids["bills"],
        ids["work"],
        ids["plain"],
    )
    return ids


async def _snapshot(connection: asyncpg.Connection) -> dict[str, list[tuple[object, ...]]]:
    state: dict[str, list[tuple[object, ...]]] = {}
    for table in (*NEW_TABLES, "list_version", "list_audit", "list_settings", "category_label"):
        columns = "mailbox_id, state, plan_hash" if table == "label_migration" else "*"  # not the time of the insert
        rows = await connection.fetch(f"select {columns} from categories.{table} order by 1, 2")  # noqa: S608
        state[table] = [tuple(row.values()) for row in rows]
    return state


async def _upgrade(url: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), "0030")


async def _rerun(url: str) -> None:
    """Run 0030 again on a database that already ran it, the way a crashed-and-restarted job would."""
    config = alembic_config(url)
    await asyncio.to_thread(command.stamp, config, "0029")
    await asyncio.to_thread(command.upgrade, config, "0030")


# --- 1: managed_label holds one row per category_label row, no list version added -----


async def test_given_0029_with_labels_when_0030_runs_then_managed_label_copies_every_row_and_no_version_is_added(
    database_url: str,
) -> None:
    connection = await _at_0029(database_url)
    try:
        ids = await _seed(connection)
        versions = await connection.fetchval("select count(*) from categories.list_version")
        audits = await connection.fetchval("select count(*) from categories.list_audit")

        await _upgrade(database_url)

        rows = await connection.fetch(
            "select mailbox_id, role, category_id, label_id, label_name from categories.managed_label order by label_id"
        )
        assert [(r["mailbox_id"], r["role"], r["category_id"], r["label_id"], r["label_name"]) for r in rows] == [
            ("mbA", "category", ids["bills"], "Label_1", "Assistant/Bills"),
            ("mbA", "category", ids["work"], "Label_2", "Assistant/Work"),
            ("mbB", "category", ids["plain"], "Label_3", "Plain"),
        ]
        assert await connection.fetchval("select count(*) from categories.list_version") == versions
        assert await connection.fetchval("select count(*) from categories.list_audit") == audits
    finally:
        await connection.close()


# --- 2 and 3: idempotent, and a half-copied state is completed without duplicates -----


async def test_given_0030_has_run_when_it_runs_again_then_nothing_changes(database_url: str) -> None:
    connection = await _at_0029(database_url)
    try:
        await _seed(connection)
        await _upgrade(database_url)
        before = await _snapshot(connection)

        await _rerun(database_url)

        assert await _snapshot(connection) == before
    finally:
        await connection.close()


async def test_given_a_crash_after_part_of_the_copy_when_0030_runs_again_then_the_data_is_complete_and_unduplicated(
    database_url: str,
) -> None:
    connection = await _at_0029(database_url)
    try:
        await _seed(connection)
        await _upgrade(database_url)
        complete = await _snapshot(connection)
        await connection.execute("delete from categories.managed_label where label_id = 'Label_2'")
        await connection.execute("delete from categories.label_migration where mailbox_id = 'mbB'")

        await _rerun(database_url)

        assert await _snapshot(connection) == complete
    finally:
        await connection.close()


# --- 4: the downgrade removes the new objects and leaves 0029 intact -----


async def test_given_0030_when_downgraded_then_the_new_objects_are_gone_and_the_old_data_is_intact(
    database_url: str,
) -> None:
    connection = await _at_0029(database_url)
    try:
        await _seed(connection)
        labels = await connection.fetch("select * from categories.category_label order by 1, 2")
        await _upgrade(database_url)

        await asyncio.to_thread(command.downgrade, alembic_config(database_url), "0029")

        tables = {
            r["table_name"]
            for r in await connection.fetch(
                "select table_name from information_schema.tables where table_schema = 'categories'"
            )
        }
        assert not tables & set(NEW_TABLES)
        columns = await connection.fetch(
            "select column_name from information_schema.columns where column_name like 'label\\_%' "
            "and table_schema = 'settings' or column_name = 'other_label'"
        )
        assert columns == []
        functions = await connection.fetch(
            "select proname from pg_proc where proname in ('confirm_label_rename', 'request_label_restore', "
            "'label_plan_hash')"
        )
        assert functions == []
        assert await connection.fetch("select * from categories.category_label order by 1, 2") == labels
        await _upgrade(database_url)  # and up again
    finally:
        await connection.close()


# --- 8: the state starts at pending with an Assistant/ label, else done -----


async def test_given_mailboxes_when_0030_has_run_then_label_migration_is_pending_with_an_assistant_label_else_done(
    database_url: str,
) -> None:
    connection = await _at_0029(database_url)
    try:
        await _seed(connection)
        await connection.execute(
            "insert into categories.gmail_label (mailbox_id, name) values ('mbC', 'Assistant/Old')"
        )
        await connection.execute("insert into categories.mailbox (id) values ('mbD')")

        await _upgrade(database_url)

        rows = await connection.fetch("select mailbox_id, state from categories.label_migration order by 1")
        assert [(r["mailbox_id"], r["state"]) for r in rows] == [
            ("mbA", "pending"),
            ("mbB", "done"),
            ("mbC", "pending"),  # a label the agent saw in Gmail counts too
            ("mbD", "done"),
        ]
    finally:
        await connection.close()


async def test_given_existing_list_settings_when_0030_runs_then_they_keep_their_archive_label_and_new_rows_default(
    database_url: str,
) -> None:
    connection = await _at_0029(database_url)
    try:
        await connection.execute("insert into categories.mailbox (id) values ('mbA')")
        async with connection.transaction():
            await connection.execute("insert into categories.list_version (mailbox_id, version) values ('mbA', 1)")
            await connection.execute(
                "insert into categories.list_settings (mailbox_id, version, archive_label) "
                "values ('mbA', 1, 'Assistant/Archive')"
            )
        await _upgrade(database_url)

        row = await connection.fetchrow("select archive_label, other_label from categories.list_settings")
        assert row is not None
        assert (row["archive_label"], row["other_label"]) == ("Assistant/Archive", "Other")
        async with connection.transaction():
            await connection.execute("insert into categories.list_version (mailbox_id, version) values ('mbA', 2)")
            await connection.execute("insert into categories.list_settings (mailbox_id, version) values ('mbA', 2)")
        fresh = await connection.fetchrow(
            "select archive_label, other_label from categories.list_settings where version = 2"
        )
        assert fresh is not None
        assert (fresh["archive_label"], fresh["other_label"]) == ("Archive", "Other")
    finally:
        await connection.close()


# --- 5: the api's rights -----


@pytest.mark.parametrize(
    "statement",
    [
        "insert into categories.managed_label (mailbox_id, role, label_id, label_name) "
        "values ('mb1', 'other', 'L1', 'Other')",
        "insert into categories.label_empty_since (mailbox_id, label_id, empty_since, last_seen_empty) "
        "values ('mb1', 'L1', now(), now())",
        "insert into categories.deleted_label (mailbox_id, label_id_hash, name) values ('mb1', repeat('a', 64), 'X')",
        "insert into categories.label_migration (mailbox_id, state) values ('mb1', 'confirmed')",
        "insert into categories.label_confirmation (mailbox_id, plan_hash) values ('mb1', repeat('a', 64))",
        "insert into categories.label_restore_request (mailbox_id) values ('mb1')",
    ],
)
async def test_given_the_api_role_when_it_writes_a_label_table_directly_then_it_is_refused(
    cat_api: asyncpg.Connection, statement: str
) -> None:
    with pytest.raises(asyncpg.PostgresError) as caught:
        await cat_api.execute(statement)
    assert sqlstate_of(caught.value) == "42501"


async def test_given_the_api_role_when_it_reads_and_calls_then_only_plan_items_and_the_two_functions_work(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await cat_owner.execute("insert into categories.label_migration (mailbox_id, state) values ('mb1', 'pending')")
    await cat_owner.execute(
        "insert into categories.label_rename_item (mailbox_id, label_id, old_name, new_name, mail_count, action) "
        "values ('mb1', 'L1', 'Assistant/Bills', 'Bills', 4, 'rename')"
    )
    for table in ("label_rename_item", "label_migration", "deleted_label"):
        await cat_api.fetch(f"select * from categories.{table}")  # noqa: S608
    for table in ("managed_label", "label_empty_since"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await cat_api.fetch(f"select * from categories.{table}")  # noqa: S608
    allowed = {
        r["proname"]
        for r in await cat_owner.fetch(
            "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'categories' and p.proname like any (array['%label%']) "
            "and has_function_privilege('web_settings_runtime', p.oid, 'EXECUTE')"
        )
    }
    assert allowed == {"confirm_label_rename", "request_label_restore"}


# --- 6: the confirmation -----


async def _plan(owner: asyncpg.Connection, mailbox: str = "mb1") -> str:
    await owner.execute("insert into categories.label_migration (mailbox_id, state) values ($1, 'pending')", mailbox)
    for label_id, old, new in (("L1", "Assistant/Bills", "Bills"), ("L2", "Assistant/Work", "Work")):
        await owner.execute(
            "insert into categories.label_rename_item (mailbox_id, label_id, old_name, new_name, mail_count, action) "
            "values ($1, $2, $3, $4, 3, 'rename')",
            mailbox,
            label_id,
            old,
            new,
        )
    plan_hash = str(await owner.fetchval("select categories.label_plan_hash($1)", mailbox))
    await owner.execute(
        "update categories.label_migration set plan_hash = $2 where mailbox_id = $1", mailbox, plan_hash
    )
    return plan_hash


async def test_given_a_plan_hash_that_does_not_match_when_the_api_confirms_then_it_is_refused_and_nothing_is_written(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await _plan(cat_owner)

    for wrong in ("0" * 64, "", "not a hash"):
        with pytest.raises(asyncpg.PostgresError) as caught:
            await cat_api.fetchval(CONFIRM, "mb1", wrong, [])
        assert sqlstate_of(caught.value) == "MC409"

    assert await cat_owner.fetchval("select count(*) from categories.label_confirmation") == 0
    assert (
        await cat_owner.fetchval("select state from categories.label_migration where mailbox_id = 'mb1'") == "pending"
    )


async def test_given_a_changed_plan_when_the_api_confirms_the_old_hash_then_it_is_refused(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    old_hash = await _plan(cat_owner)
    await cat_owner.execute("update categories.label_rename_item set new_name = 'Other name' where label_id = 'L1'")

    with pytest.raises(asyncpg.PostgresError) as caught:
        await cat_api.fetchval(CONFIRM, "mb1", old_hash, [])

    assert sqlstate_of(caught.value) == "MC409"
    assert await cat_owner.fetchval("select count(*) from categories.label_confirmation") == 0


async def test_given_the_right_hash_when_the_api_confirms_twice_then_one_confirmation_exists_and_the_state_is_confirmed(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan_hash = await _plan(cat_owner)

    first = await cat_api.fetchval(CONFIRM, "mb1", plan_hash, ["L2"])
    second = await cat_api.fetchval(CONFIRM, "mb1", plan_hash, ["L2"])

    assert first == second
    row = await cat_owner.fetchrow("select * from categories.label_confirmation")
    assert row is not None
    assert (row["plan_hash"], row["skipped_ids"], row["channel"]) == (plan_hash, ["L2"], "web")
    assert row["actor_digest"] != "0" * 64
    assert await cat_owner.fetchval("select count(*) from categories.label_confirmation") == 1
    assert (
        await cat_owner.fetchval("select state from categories.label_migration where mailbox_id = 'mb1'") == "confirmed"
    )


async def test_given_a_confirmation_when_the_api_confirms_with_other_skips_or_skips_an_unknown_label_then_refused(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan_hash = await _plan(cat_owner)
    with pytest.raises(asyncpg.PostgresError) as unknown:
        await cat_api.fetchval(CONFIRM, "mb1", plan_hash, ["nope"])
    assert sqlstate_of(unknown.value) == "MC409"

    await cat_api.fetchval(CONFIRM, "mb1", plan_hash, [])
    with pytest.raises(asyncpg.PostgresError) as other:
        await cat_api.fetchval(CONFIRM, "mb1", plan_hash, ["L1"])
    assert sqlstate_of(other.value) == "MC409"


async def test_given_the_agent_when_it_sets_the_state_to_confirmed_then_the_guard_refuses(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _plan(cat_owner)

    with pytest.raises(asyncpg.PostgresError) as caught:
        await cat_agent.execute("update categories.label_migration set state = 'confirmed' where mailbox_id = 'mb1'")

    assert sqlstate_of(caught.value) == "MC409"


async def test_given_a_restore_request_when_the_api_asks_twice_then_one_open_request_exists(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    plan_hash = await _plan(cat_owner)
    with pytest.raises(asyncpg.PostgresError) as early:
        await cat_api.fetchval(RESTORE, "mb1")  # nothing was renamed yet
    assert sqlstate_of(early.value) == "MC409"
    await cat_api.fetchval(CONFIRM, "mb1", plan_hash, [])

    first = await cat_api.fetchval(RESTORE, "mb1")
    second = await cat_api.fetchval(RESTORE, "mb1")

    assert first == second
    assert await cat_owner.fetchval("select count(*) from categories.label_restore_request") == 1


# --- 7: the settings bounds -----


@pytest.fixture
async def schedule_row(cat_owner: asyncpg.Connection) -> asyncpg.Connection:
    await cat_owner.execute(
        "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, "
        "updated_by) values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', 'u1')"
    )
    return cat_owner


async def test_given_a_fresh_schedule_row_then_the_label_settings_carry_their_defaults(
    schedule_row: asyncpg.Connection,
) -> None:
    row = await schedule_row.fetchrow(
        "select label_wait_minutes, label_protection_days, label_retention_days from settings.schedule"
    )
    assert row is not None
    assert (row["label_wait_minutes"], row["label_protection_days"], row["label_retention_days"]) == (720, 7, 30)


@pytest.mark.parametrize(("column", "value"), BOUNDS)
@pytest.mark.parametrize("role", ["owner", "api", "agent"])
async def test_given_a_value_outside_its_bounds_when_any_role_writes_it_then_the_check_refuses(
    schedule_row: asyncpg.Connection, cat_url: str, role: str, column: str, value: int
) -> None:
    from tests.db.conftest import AGENT_ROLE, API_ROLE, connect_as  # noqa: PLC0415

    connection = await connect_as(cat_url, {"owner": None, "api": API_ROLE, "agent": AGENT_ROLE}[role])
    try:
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                f"update settings.schedule set {column} = $1, version = 2, updated_via = $2, updated_by = $3",  # noqa: S608
                value,
                "telegram" if role == "agent" else "web",
                "agent" if role == "agent" else "web:" + "a" * 32,
            )
    finally:
        await connection.close()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("label_wait_minutes", 5),
        ("label_wait_minutes", 720),
        ("label_protection_days", 1),
        ("label_protection_days", 30),
        ("label_retention_days", 7),
        ("label_retention_days", 90),
    ],
)
async def test_given_a_value_at_its_edge_when_the_api_writes_it_then_it_is_saved(
    schedule_row: asyncpg.Connection, cat_api: asyncpg.Connection, column: str, value: int
) -> None:
    await cat_api.execute(
        f"update settings.schedule set {column} = $1, version = 2, updated_via = 'web', "  # noqa: S608
        "updated_by = 'web:' || repeat('a', 32)",
        value,
    )
    assert await schedule_row.fetchval(f"select {column} from settings.schedule") == value  # noqa: S608


async def test_given_the_other_label_when_it_is_empty_or_too_long_then_the_check_refuses(
    cat_owner: asyncpg.Connection,
) -> None:
    for name in ("", "x" * 226):
        async with cat_owner.transaction():
            await cat_owner.execute("insert into categories.list_version (mailbox_id, version) values ('mb1', 1)")
            with pytest.raises(asyncpg.CheckViolationError):
                await cat_owner.execute(
                    "insert into categories.list_settings (mailbox_id, version, other_label) values ('mb1', 1, $1)",
                    name,
                )
