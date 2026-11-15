"""U-mail-categories-03, criteria 3 to 5: list versions are insert-only, derived by the database and audited."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

import asyncpg
import pytest

from tests.db.conftest import AGENT_ROLE, API_ROLE, connect_as, insert_list, write_list


def _digest(role: str) -> str:
    return hashlib.sha256(role.encode()).hexdigest()


async def _audit(owner: asyncpg.Connection, mailbox: str = "mb1") -> list[asyncpg.Record]:
    return await owner.fetch(
        "select version, old_list, new_list, channel, actor_digest, at from categories.list_audit "
        "where mailbox_id = $1 order by version",
        mailbox,
    )


def _names(value: str) -> list[str]:
    return [item["name"] for item in json.loads(value)]


async def test_given_a_new_version_when_the_api_writes_it_then_it_is_stored_with_one_derived_audit_record(
    cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_api, "mb1", 1, ["Bills", "Travel"])
    await write_list(cat_api, "mb1", 2, ["Bills", "Trips"])

    versions = await cat_owner.fetch("select version, created_via, created_by from categories.list_version order by 1")
    assert [(r["version"], r["created_via"], r["created_by"]) for r in versions] == [
        (1, "web", _digest(API_ROLE)),
        (2, "web", _digest(API_ROLE)),
    ]
    rows = await _audit(cat_owner)
    assert [(r["version"], r["channel"], r["actor_digest"]) for r in rows] == [
        (1, "web", _digest(API_ROLE)),
        (2, "web", _digest(API_ROLE)),
    ]
    assert [_names(r["old_list"]) for r in rows] == [[], ["Bills", "Travel"]]
    assert [_names(r["new_list"]) for r in rows] == [["Bills", "Travel"], ["Bills", "Trips"]]
    assert await cat_owner.fetchval("select max(at) > now() - interval '1 minute' from categories.list_audit")


async def test_given_the_agent_when_it_seeds_a_version_then_the_channel_is_telegram_and_the_digest_is_its_own(
    cat_agent: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_agent, "mb1", 1, ["Bills"])

    rows = await _audit(cat_owner)
    assert [(r["channel"], r["actor_digest"]) for r in rows] == [("telegram", _digest(AGENT_ROLE))]


@pytest.mark.parametrize("column", ["created_at", "created_via", "created_by"])
async def test_given_a_writer_that_names_a_derived_column_when_it_inserts_then_postgres_refuses_it(
    cat_api: asyncpg.Connection, column: str
) -> None:
    value = "now()" if column == "created_at" else "'telegram'"

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await cat_api.execute(
            f"insert into categories.list_version (mailbox_id, version, {column}) values ('mb1', 1, {value})"
        )


async def test_given_a_list_without_categories_when_it_is_written_then_it_is_stored_and_audited_as_empty(
    cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_api, "mb1", 1, [])

    assert [_names(r["new_list"]) for r in await _audit(cat_owner)] == [[]]


async def test_given_two_inserts_for_one_version_when_they_race_then_one_wins_and_the_other_is_a_unique_violation(
    cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection, cat_url: str
) -> None:
    await write_list(cat_api, "mb1", 1, ["Bills"])
    other = await connect_as(cat_url, API_ROLE)
    try:
        first = cat_api.transaction()
        await first.start()
        await insert_list(cat_api, "mb1", 2, ["Bills", "Travel"])
        second = other.transaction()
        await second.start()
        loser = asyncio.create_task(insert_list(other, "mb1", 2, ["Bills", "Trips"]))
        for _ in range(100):  # wait until the second insert is blocked on the first one's key
            if await cat_owner.fetchval("select count(*) from pg_stat_activity where wait_event_type = 'Lock'"):
                break
            await asyncio.sleep(0.05)
        await first.commit()

        with pytest.raises(asyncpg.UniqueViolationError):
            await loser
        await second.rollback()
    finally:
        await other.close()

    assert await cat_owner.fetchval("select count(*) from categories.list_version where version = 2") == 1
    assert [_names(r["new_list"]) for r in await _audit(cat_owner)] == [["Bills"], ["Bills", "Travel"]]


async def test_given_a_category_for_an_older_version_when_inserted_in_a_later_transaction_then_it_is_refused(
    cat_api: asyncpg.Connection,
) -> None:
    await write_list(cat_api, "mb1", 1, ["Bills"])
    identity = uuid.uuid4()
    await cat_api.execute("insert into categories.category_identity (mailbox_id, id) values ('mb1', $1)", identity)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await cat_api.execute(
            "insert into categories.category (mailbox_id, version, id, name, position) "
            "values ('mb1', 1, $1, 'Extra', 5)",
            identity,
        )


@pytest.mark.parametrize("version", [2, 3, 5])
async def test_given_a_first_version_above_one_when_it_is_written_then_the_deferred_trigger_refuses_the_commit(
    cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection, version: int
) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await write_list(cat_api, "mb1", version, ["Bills"])

    assert await cat_owner.fetchval("select count(*) from categories.list_version") == 0
    assert await cat_owner.fetchval("select count(*) from categories.list_audit") == 0


@pytest.mark.parametrize("version", [4, 5])
async def test_given_a_gap_in_the_versions_when_it_is_written_then_the_deferred_trigger_refuses_the_commit(
    cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection, version: int
) -> None:
    await write_list(cat_api, "mb1", 1, ["Bills"])
    await write_list(cat_api, "mb1", 2, ["Bills", "Travel"])

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await write_list(cat_api, "mb1", version, ["Bills"])

    assert await cat_owner.fetchval("select max(version) from categories.list_version") == 2
    assert await cat_owner.fetchval("select count(*) from categories.list_audit") == 2


async def test_given_a_second_mailbox_when_it_writes_its_first_version_then_its_numbering_is_its_own(
    cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_api, "mb1", 1, ["Bills"])
    await write_list(cat_api, "mb1", 2, ["Bills", "Travel"])

    await write_list(cat_api, "mb2", 1, ["Work"])

    assert [(r["version"], _names(r["new_list"])) for r in await _audit(cat_owner, "mb2")] == [(1, ["Work"])]


async def test_given_an_update_or_delete_of_a_list_row_when_the_api_tries_it_then_postgres_refuses_it(
    cat_api: asyncpg.Connection,
) -> None:
    await write_list(cat_api, "mb1", 1, ["Bills"])

    for statement in (
        "update categories.category set name = 'X'",
        "delete from categories.category",
        "update categories.list_version set version = 9",
        "delete from categories.list_version",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await cat_api.execute(statement)
