"""U-mail-categories-03, criteria 6 and 7 (AC-56, ADR-0047): ``purge_expired()`` and the append-only audit tables."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import json

import asyncpg
import pytest

from tests.db.conftest import write_list

OLD = "now() - interval '400 days'"  # past every retention
YOUNG = "now() - interval '300 days'"  # inside the one-year retentions
CHAT = 4242
AUDIT_VERSION = {"o": 901, "y": 902, "n": 903}  # list_audit has a key (mailbox, version): one version per seeded age


async def _purge(connection: asyncpg.Connection) -> dict[str, int]:
    return json.loads(str(await connection.fetchval("select categories.purge_expired()")))


async def _seed_rows(owner: asyncpg.Connection, age: str, tag: str, *, expires_age: str) -> None:
    """One row of every purged table, backdated by ``age`` (``expires_age`` for the Telegram action)."""
    await owner.execute(
        f"insert into categories.list_audit (mailbox_id, version, old_list, new_list, channel, actor_digest, at) "
        f"values ('mb2', {AUDIT_VERSION[tag]}, '[]', '[]', 'web', '{'a' * 64}', {age})"
    )
    await owner.execute(
        "insert into categories.filing (mailbox_id, message_id, list_version, topic_id, filed_at) "
        f"values ('mb2', '{tag}', 1, '{'0' * 8}-0000-0000-0000-000000000000', {age})"
    )
    await owner.execute(
        "insert into categories.telegram_action (mailbox_id, nonce_hash, chat_id, kind, target, expires_at) "
        f"values ('mb2', '{tag * 64}'::char(64), {CHAT}, 'undo', 'v2', {expires_age})"
    )


async def _counts(owner: asyncpg.Connection) -> dict[str, int]:
    tables = ("list_audit", "filing", "telegram_action", "rejection", "list_version", "category")
    return {t: int(str(await owner.fetchval(f"select count(*) from categories.{t}"))) for t in tables}


async def test_given_young_rows_when_the_agent_purges_with_a_changed_session_clock_then_they_survive(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _seed_rows(cat_owner, YOUNG, "y", expires_age="now() - interval '6 days'")
    before = await _counts(cat_owner)

    await cat_agent.execute("set timezone = 'Pacific/Kiritimati'")  # the clock the session sees changes
    await cat_agent.execute("set datestyle = 'SQL, DMY'")
    # a look-alike now() in the agent's own temp schema must not win over the pinned search path
    await cat_agent.execute(
        "create function pg_temp.now() returns timestamptz language sql as $$ select 'infinity'::timestamptz $$"
    )
    await cat_agent.execute("set search_path = pg_temp, public")
    counts = await _purge(cat_agent)

    assert await _counts(cat_owner) == before
    assert sum(counts.values()) == 0


async def test_given_the_agent_when_it_deletes_from_an_audit_table_directly_then_postgres_refuses_it(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _seed_rows(cat_owner, OLD, "o", expires_age="now() - interval '10 days'")

    for table in ("list_audit", "filing", "rejection", "list_version", "category", "telegram_action"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await cat_agent.execute(f"delete from categories.{table}")
    assert (await _counts(cat_owner))["list_audit"] == 1


async def test_given_backdated_rows_when_the_purge_runs_then_only_the_rows_past_their_retention_go(
    cat_owner: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await _seed_rows(cat_owner, OLD, "o", expires_age="now() - interval '10 days'")
    await _seed_rows(cat_owner, YOUNG, "y", expires_age="now() - interval '6 days'")
    await _seed_rows(cat_owner, "now()", "n", expires_age="now() + interval '1 hour'")

    counts = await _purge(cat_agent)

    assert counts["list_audit"] == counts["filing"] == counts["telegram_action"] == 1
    assert (await _counts(cat_owner))["list_audit"] == 2
    assert await cat_owner.fetchval("select count(*) from categories.filing where message_id = 'o'") == 0
    assert await cat_owner.fetchval("select count(*) from categories.filing where message_id in ('y', 'n')") == 2
    assert await cat_owner.fetchval("select count(*) from categories.telegram_action") == 2


async def test_given_replaced_versions_when_the_purge_runs_then_only_those_replaced_over_a_year_ago_go(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    for version in (1, 2, 3, 4):
        await write_list(cat_api, "mb1", version, [f"C{version}"])
    # v1 was replaced 400 days ago, v2 300 days ago, v3 just now: v4 is current. created_at of the next one counts.
    await cat_owner.execute("alter table categories.list_version disable trigger user")
    await cat_owner.execute(f"update categories.list_version set created_at = {OLD} where version = 2")
    await cat_owner.execute(f"update categories.list_version set created_at = {YOUNG} where version = 3")
    await cat_owner.execute("alter table categories.list_version enable trigger user")

    counts = await _purge(cat_agent)

    assert counts["list_version"] == 1
    assert counts["category"] == 1
    remaining = await cat_owner.fetch("select version from categories.list_version order by 1")
    assert [r["version"] for r in remaining] == [2, 3, 4]
    assert await cat_owner.fetchval("select count(*) from categories.category where version = 1") == 0
    assert await cat_owner.fetchval("select count(*) from categories.category where version = 2") == 1


async def test_given_a_current_list_when_it_is_over_a_year_old_then_the_purge_keeps_it(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await write_list(cat_api, "mb1", 1, ["Bills"])
    await cat_owner.execute(f"update categories.list_version set created_at = {OLD}")

    await _purge(cat_agent)

    assert (await _counts(cat_owner))["list_version"] == 1


async def test_given_rejections_when_the_list_changes_then_the_purge_keeps_only_the_current_lists_ones(
    cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection, cat_agent: asyncpg.Connection
) -> None:
    await write_list(cat_api, "mb1", 1, ["Bills"])
    await cat_agent.execute(
        "insert into categories.rejection (mailbox_id, message_id, list_version) values ('mb1', 'm1', 1)"
    )
    assert (await _purge(cat_agent))["rejection"] == 0
    assert await cat_owner.fetchval("select count(*) from categories.rejection") == 1

    await write_list(cat_api, "mb1", 2, ["Bills", "Travel"])
    await cat_agent.execute(
        "insert into categories.rejection (mailbox_id, message_id, list_version) values ('mb1', 'm2', 2)"
    )
    counts = await _purge(cat_agent)

    assert counts["rejection"] == 1
    assert [r["message_id"] for r in await cat_owner.fetch("select message_id from categories.rejection")] == ["m2"]


async def test_given_the_purge_function_when_its_signature_is_read_then_it_takes_no_parameters_and_is_the_definers(
    cat_owner: asyncpg.Connection,
) -> None:
    row = await cat_owner.fetchrow(
        "select pronargs, prosecdef, proconfig from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'categories' and p.proname = 'purge_expired'"
    )

    assert row is not None
    assert row["pronargs"] == 0
    assert row["prosecdef"] is True
    assert any(setting.startswith("search_path=pg_catalog") for setting in row["proconfig"])


async def test_given_the_api_role_when_it_calls_the_purge_then_postgres_refuses_it(
    cat_api: asyncpg.Connection,
) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await cat_api.fetchval("select categories.purge_expired()")
