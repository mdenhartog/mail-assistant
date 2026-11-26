"""U-label-structure-05: revision 0024, the additive migration for contract v2 (ADR-0053, ADR-0058, ADR-0059)."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic import command

from app.db.migrate import RUNTIME_ROLE, WEB_ROLE, migrate_database
from app.settings import SettingsError, load_migrate_settings
from category_policy import ARCHIVE_LABEL_DEFAULT
from tests.db.conftest import alembic_config, plain_url

if TYPE_CHECKING:
    from alembic.config import Config

PREVIOUS = "0023"
THIS = "0024"  # the revision of this file; the filing code switch of revision 0025 has its own tests
NEW_TABLES = ("category_sender", "list_settings", "upload_preview")
DEFAULT_ARCHIVE = "Assistant/Archive"
JOB_PASSWORDS = {RUNTIME_ROLE: "runtime-job-test-only", WEB_ROLE: "web-job-test-only"}
JOB_ENV = {
    "DATABASE_OWNER_URL": "postgresql+asyncpg://owner:test-pw@localhost/db",
    "RUNTIME_ROLE_PASSWORD": "test-runtime",
    "WEB_ROLE_PASSWORD": "test-web",
}


async def _up(config: Config, revision: str = "head") -> None:
    await asyncio.to_thread(command.upgrade, config, revision)


async def _down(config: Config, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, config, revision)


async def _seed_v1_list(connection: asyncpg.Connection, versions: int = 2) -> list[uuid.UUID]:
    """An INT-004 list of two categories, written as ``versions`` versions, plus a label and a filing."""
    ids = [uuid.uuid4(), uuid.uuid4()]
    await connection.execute("insert into categories.mailbox (id) values ('mb')")
    for version in range(1, versions + 1):
        async with connection.transaction():
            await connection.execute(
                "insert into categories.list_version (mailbox_id, version) values ('mb', $1)", version
            )
            for position, identity in enumerate(ids):
                if version == 1:
                    await connection.execute(
                        "insert into categories.category_identity (mailbox_id, id) values ('mb', $1)", identity
                    )
                await connection.execute(
                    "insert into categories.category (mailbox_id, version, id, name, description, position) "
                    "values ('mb', $1, $2, $3, 'about', $4)",
                    version,
                    identity,
                    f"Name{position}",
                    position,
                )
    await connection.execute(
        "insert into categories.category_label (mailbox_id, category_id, label_id, label_name) "
        "values ('mb', $1, 'Label_1', 'Assistant/Name0')",
        ids[0],
    )
    await connection.execute(
        "insert into categories.filing (mailbox_id, message_id, list_version, category_id) values ('mb', 'm1', 1, $1)",
        ids[0],
    )
    return ids


async def _columns(connection: asyncpg.Connection, table: str) -> set[str]:
    rows = await connection.fetch(
        "select column_name from information_schema.columns where table_schema = 'categories' and table_name = $1",
        table,
    )
    return {r["column_name"] for r in rows}


async def _tables(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch("select tablename from pg_tables where schemaname = 'categories'")
    return {r["tablename"] for r in rows}


async def _list_state(connection: asyncpg.Connection) -> tuple[list[asyncpg.Record], ...]:
    return (
        await connection.fetch(
            "select mailbox_id, version, id, name, description, position from categories.category order by 1, 2, 3"
        ),
        await connection.fetch("select * from categories.list_version order by 1, 2"),
        await connection.fetch(  # the columns of revision 0014 (0028 adds the instructions)
            "select mailbox_id, version, old_list, new_list, channel, actor_digest, at "
            "from categories.list_audit order by 1, 2"
        ),
        await connection.fetch("select * from categories.category_label order by 1, 2"),
    )


# --- 1: the INT-004 list becomes topics ------------------------------------------------------------------------------
async def test_given_the_int004_list_when_the_migration_runs_then_every_category_is_a_topic_and_nothing_is_added(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await _up(config, PREVIOUS)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        ids = await _seed_v1_list(connection)
        before = await _list_state(connection)

        await _up(config, THIS)

        assert await _list_state(connection) == before
        rows = await connection.fetch("select kind, notify from categories.category")
        assert {(r["kind"], r["notify"]) for r in rows} == {("topic", False)}
        assert await connection.fetchval("select count(*) from categories.category_sender") == 0
        filing = await connection.fetchrow("select * from categories.filing where message_id = 'm1'")
        assert filing is not None
        assert (filing["category_id"], filing["topic_id"], filing["extra_id"]) == (ids[0], ids[0], None)
        assert (filing["source"], filing["source_ref"]) == ("model", None)
    finally:
        await connection.close()


@pytest.mark.parametrize("source", ["model", "sender_rule", "sender_rule_not_applied"])
async def test_given_a_filing_source_when_it_is_inserted_then_the_three_values_are_accepted(
    cat_owner: asyncpg.Connection, source: str
) -> None:
    await cat_owner.execute(
        "insert into categories.filing (mailbox_id, message_id, list_version, topic_id, source) "
        "values ('mb1', 's', 1, $1, $2)",
        uuid.uuid4(),
        source,
    )


async def test_given_an_unknown_filing_source_when_it_is_inserted_then_a_check_refuses_it(
    cat_owner: asyncpg.Connection,
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match="ck_filing_source"):
        await cat_owner.execute(
            "insert into categories.filing (mailbox_id, message_id, list_version, topic_id, source) "
            "values ('mb1', 's', 1, $1, 'guess')",
            uuid.uuid4(),
        )


async def test_given_a_category_kind_when_it_is_not_topic_or_extra_then_a_check_refuses_it(
    cat_owner: asyncpg.Connection,
) -> None:
    await cat_owner.execute("insert into categories.list_version (mailbox_id, version) values ('mb1', 1)")
    identity = uuid.uuid4()
    await cat_owner.execute("insert into categories.category_identity (mailbox_id, id) values ('mb1', $1)", identity)
    with pytest.raises(asyncpg.CheckViolationError, match="ck_category_kind"):
        await cat_owner.execute(
            "insert into categories.category (mailbox_id, version, id, name, position, kind) "
            "values ('mb1', 1, $1, 'n', 0, 'other')",
            identity,
        )


# --- 2: idempotent, reversible ---------------------------------------------------------------------------------------
async def test_given_the_migration_ran_when_it_runs_again_and_is_downgraded_then_the_old_shape_is_back(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await _up(config, PREVIOUS)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        ids = await _seed_v1_list(connection)
        old_tables = await _tables(connection)
        old_category = await _columns(connection, "category")
        old_filing = await _columns(connection, "filing")
        before = await _list_state(connection)

        await _up(config)
        await _up(config)
        assert await _list_state(connection) == before
        assert set(NEW_TABLES) <= await _tables(connection)

        await _down(config, PREVIOUS)

        assert await _tables(connection) == old_tables
        assert await _columns(connection, "category") == old_category
        assert await _columns(connection, "filing") == old_filing
        assert await connection.fetchval("select category_id from categories.filing where message_id = 'm1'") == ids[0]
        assert await _list_state(connection) == before

        await _up(config)  # and up again
        assert set(NEW_TABLES) <= await _tables(connection)
    finally:
        await connection.close()


async def test_given_the_downgrade_when_filings_were_written_after_the_migration_then_category_id_keeps_them(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await _up(config)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        identity = uuid.uuid4()
        await connection.execute("insert into categories.mailbox (id) values ('mb')")
        await connection.execute(
            "insert into categories.filing (mailbox_id, message_id, list_version, topic_id, source_ref) "
            "values ('mb', 'late', 1, $1, 'a@example.com')",
            identity,
        )

        await _down(config, PREVIOUS)

        assert (
            await connection.fetchval("select category_id from categories.filing where message_id = 'late'") == identity
        )
    finally:
        await connection.close()


# --- 3: the archive label --------------------------------------------------------------------------------------------
async def test_given_a_custom_archive_label_when_the_migration_runs_then_every_migrated_version_stores_it(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await _up(config, PREVIOUS)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await _seed_v1_list(connection)
        config.attributes["archive_label"] = "Old mail/Done"

        await _up(config)

        rows = await connection.fetch(
            "select version, general_instructions, archive_label from categories.list_settings"
        )
        assert {(r["version"], r["general_instructions"], r["archive_label"]) for r in rows} == {
            (1, "", "Old mail/Done"),
            (2, "", "Old mail/Done"),
        }
    finally:
        await connection.close()


async def test_given_no_archive_label_when_the_migration_runs_then_the_default_is_stored(database_url: str) -> None:
    config = alembic_config(database_url)
    await _up(config, PREVIOUS)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await _seed_v1_list(connection, versions=1)

        await _up(config)

        assert await connection.fetchval("select archive_label from categories.list_settings") == DEFAULT_ARCHIVE
    finally:
        await connection.close()


async def _restore_shared_passwords(connection: asyncpg.Connection) -> None:
    """The migrate job sets its own role passwords; the roles are shared in the container, so put theirs back."""
    await connection.execute(f"ALTER ROLE {RUNTIME_ROLE} PASSWORD 'runtime-test-only'")
    await connection.execute(f"ALTER ROLE {WEB_ROLE} PASSWORD 'web-test-password'")


async def test_given_a_custom_archive_label_when_the_migrate_job_runs_then_the_migrated_rows_hold_it(
    database_url: str,
) -> None:
    await _up(alembic_config(database_url), PREVIOUS)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await _seed_v1_list(connection, versions=1)

        await migrate_database(database_url, JOB_PASSWORDS, archive_label="Mail/Done")

        assert await connection.fetchval("select archive_label from categories.list_settings") == "Mail/Done"
    finally:
        await _restore_shared_passwords(connection)
        await connection.close()


async def test_given_no_archive_label_when_the_migrate_job_runs_then_the_default_is_stored(database_url: str) -> None:
    await _up(alembic_config(database_url), PREVIOUS)
    connection = await asyncpg.connect(plain_url(database_url))
    try:
        await _seed_v1_list(connection, versions=1)

        await migrate_database(database_url, JOB_PASSWORDS)

        assert await connection.fetchval("select archive_label from categories.list_settings") == DEFAULT_ARCHIVE
    finally:
        await _restore_shared_passwords(connection)
        await connection.close()


def test_given_the_job_environment_when_it_holds_archive_label_then_the_settings_carry_it() -> None:
    # the settings default is the prefix-free policy default (spec AC 12); 0024 keeps its own legacy default
    assert load_migrate_settings(JOB_ENV).archive_label == ARCHIVE_LABEL_DEFAULT
    assert load_migrate_settings({**JOB_ENV, "ARCHIVE_LABEL": "Mail/Done"}).archive_label == "Mail/Done"


@pytest.mark.parametrize("label", ["", "INBOX", "Assistant/Other", " padded", "a//b"])
def test_given_an_unusable_archive_label_when_the_settings_load_then_the_job_refuses_it(label: str) -> None:
    with pytest.raises(SettingsError, match="ARCHIVE_LABEL"):
        load_migrate_settings({**JOB_ENV, "ARCHIVE_LABEL": label})


# --- the version rules of the new insert-only tables -----------------------------------------------------------------
async def _version_with_category(connection: asyncpg.Connection, mailbox: str, version: int) -> uuid.UUID:
    identity = uuid.uuid4()
    await connection.execute(
        "insert into categories.list_version (mailbox_id, version) values ($1, $2)", mailbox, version
    )
    await connection.execute(
        "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", mailbox, identity
    )
    await connection.execute(
        "insert into categories.category (mailbox_id, version, id, name, position) values ($1, $2, $3, 'n', 0)",
        mailbox,
        version,
        identity,
    )
    return identity


async def test_given_a_new_version_when_senders_and_settings_are_written_in_the_same_transaction_then_they_are_kept(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    async with cat_api.transaction():
        identity = await _version_with_category(cat_api, "mb1", 1)
        await cat_api.execute(
            "insert into categories.category_sender (mailbox_id, version, category_id, entry, is_domain) "
            "values ('mb1', 1, $1, 'example.com', true)",
            identity,
        )
        await cat_api.execute(
            "insert into categories.list_settings (mailbox_id, version, general_instructions, archive_label) "
            "values ('mb1', 1, 'be brief', $1)",
            DEFAULT_ARCHIVE,
        )

    row = await cat_owner.fetchrow("select entry, is_domain, subdomains from categories.category_sender")
    assert row is not None
    assert (row["entry"], row["is_domain"], row["subdomains"]) == ("example.com", True, False)


async def test_given_an_old_version_when_a_sender_or_settings_row_is_added_later_then_42501(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    async with cat_api.transaction():
        identity = await _version_with_category(cat_api, "mb1", 1)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await cat_api.execute(
            "insert into categories.category_sender (mailbox_id, version, category_id, entry, is_domain) "
            "values ('mb1', 1, $1, 'late.example.com', true)",
            identity,
        )
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await cat_api.execute(
            "insert into categories.list_settings (mailbox_id, version, archive_label) values ('mb1', 1, $1)",
            DEFAULT_ARCHIVE,
        )
    assert await cat_owner.fetchval("select count(*) from categories.category_sender") == 0


async def test_given_the_limits_when_settings_break_them_then_a_check_refuses_it(
    cat_owner: asyncpg.Connection,
) -> None:
    insert = (
        "insert into categories.list_settings (mailbox_id, version, general_instructions, archive_label) "
        "values ('mb1', 1, $1, $2)"
    )
    async with cat_owner.transaction():
        await cat_owner.execute("insert into categories.list_version (mailbox_id, version) values ('mb1', 1)")
        for instructions, label, constraint in (
            ("x" * 4001, "a", "ck_list_settings_instructions"),
            ("", "", "ck_list_settings_archive_label"),
        ):
            with pytest.raises(asyncpg.CheckViolationError, match=constraint):
                async with cat_owner.transaction():
                    await cat_owner.execute(insert, instructions, label)
        await cat_owner.execute(insert, "x" * 4000, "a")

    assert await cat_owner.fetchval("select count(*) from categories.list_settings") == 1


# --- 5: one alert per mail -------------------------------------------------------------------------------------------
async def test_given_two_alerts_for_one_mail_when_the_second_is_inserted_then_the_unique_key_refuses_it(
    cat_owner: asyncpg.Connection,
) -> None:
    mail_id = await cat_owner.fetchval(
        "insert into mail_item (gmail_message_id, thread_id, urgent, created_at) values ('g1', 't1', false, now()) "
        "returning id"
    )
    insert = "insert into alert (mail_item_id, state, created_at, updated_at) values ($1, 'new', now(), now())"
    await cat_owner.execute(insert, mail_id)

    with pytest.raises(asyncpg.UniqueViolationError):
        await cat_owner.execute(insert, mail_id)


# --- 6: the purge ----------------------------------------------------------------------------------------------------
_PREVIEW = (
    "insert into categories.upload_preview "
    "(mailbox_id, id, session_digest, file_hash, base_version, content, expires_at) "
    "values ('mb1', $1, $2, $3, 1, 'schema: 1', {expires})"
)


async def test_given_expired_and_live_previews_when_the_purge_runs_then_only_the_expired_one_goes(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    gone, young, live = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ages = ((gone, "now() - interval '2 hours'"), (young, "now() - interval '5 minutes'"))
    for identity, expires in (*ages, (live, "now() + interval '10 minutes'")):
        await cat_owner.execute(_PREVIEW.format(expires=expires), identity, "d" * 64, "f" * 64)
    mailboxes = await cat_owner.fetchval("select count(*) from categories.mailbox")

    removed = json.loads(str(await cat_agent.fetchval("select categories.purge_expired()")))

    assert removed["upload_preview"] == 1
    assert {r["id"] for r in await cat_owner.fetch("select id from categories.upload_preview")} == {young, live}
    assert await cat_owner.fetchval("select count(*) from categories.mailbox") == mailboxes


async def test_given_an_old_version_with_senders_and_settings_when_the_purge_runs_then_they_go_with_it(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    async with cat_owner.transaction():
        identity = await _version_with_category(cat_owner, "mb1", 1)
        await cat_owner.execute(
            "insert into categories.category_sender (mailbox_id, version, category_id, entry, is_domain) "
            "values ('mb1', 1, $1, 'example.com', true)",
            identity,
        )
        await cat_owner.execute(
            "insert into categories.list_settings (mailbox_id, version, archive_label) values ('mb1', 1, $1)",
            DEFAULT_ARCHIVE,
        )
    async with cat_owner.transaction():
        await cat_owner.execute("insert into categories.list_version (mailbox_id, version) values ('mb1', 2)")
        await cat_owner.execute(
            "update categories.list_version set created_at = now() - interval '400 days' where version = 2"
        )

    await cat_agent.fetchval("select categories.purge_expired()")

    assert await cat_owner.fetchval("select count(*) from categories.category_sender") == 0
    assert await cat_owner.fetchval("select count(*) from categories.list_settings") == 0
    assert await cat_owner.fetchval("select count(*) from categories.list_version") == 1
