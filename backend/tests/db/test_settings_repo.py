"""U-web-settings-21: the settings write repository against a real PostgreSQL, written as the web role.

The audit table is read as the owner: the web role has no privilege on it.
"""

import asyncio
import logging
from datetime import time

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import Database
from app.settings_repo import SettingsRepository, StoredSettings, VersionConflict
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy

ACTOR = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"
CANARY_ZONE = "Pacific/Kiritimati"
AUDIT = "select via, by, db_role, old, new from settings.settings_change order by (new->>'version')::int"
NEW_YORK = TimePolicy("America/New_York", time(22, 30), time(6, 45), time(18, 5), time(9, 15))
BREAK_AUDIT = (
    "CREATE OR REPLACE FUNCTION settings.settings_audit() RETURNS trigger LANGUAGE plpgsql AS "
    "$$ BEGIN RAISE EXCEPTION 'audit down'; END $$"
)


def _times(policy: TimePolicy) -> tuple[time, time, time, time]:
    return policy.quiet_start, policy.quiet_end, policy.overview_at, policy.remind_at


@pytest.fixture
def repo(web_database: Database) -> SettingsRepository:
    return SettingsRepository(web_database)


# Criterion 1
async def test_given_no_row_when_written_at_version_0_then_version_1_and_a_second_writer_conflicts(
    repo: SettingsRepository, owner: asyncpg.Connection
) -> None:
    stored = await repo.write(NEW_YORK, 0, ACTOR)

    assert (stored.policy, stored.version, stored.updated_via) == (NEW_YORK, 1, "web")
    assert stored.updated_at is not None
    assert await repo.read() == stored
    assert await owner.fetchval("select count(*) from settings.schedule") == 1
    with pytest.raises(VersionConflict) as conflict:
        await repo.write(DEFAULT_POLICY, 0, OTHER)
    assert conflict.value.current == stored


# Criterion 2
async def test_given_a_write_at_version_1_when_committed_then_version_2_and_one_audit_record_per_change(
    repo: SettingsRepository, owner: asyncpg.Connection
) -> None:
    await repo.write(DEFAULT_POLICY, 0, OTHER)

    stored = await repo.write(NEW_YORK, 1, ACTOR)

    assert (stored.policy, stored.version) == (NEW_YORK, 2)
    rows = await owner.fetch(AUDIT)
    assert len(rows) == 2
    last = rows[-1]
    assert (last["via"], last["by"], last["db_role"]) == ("web", f"web:{ACTOR}", "web_settings_runtime")
    assert rows[0]["by"] == f"web:{OTHER}"


# Criterion 3
async def test_given_two_sessions_on_the_same_version_when_both_write_then_exactly_one_wins(
    web_database: Database, owner: asyncpg.Connection
) -> None:
    first, second = SettingsRepository(web_database), SettingsRepository(web_database)
    await first.write(DEFAULT_POLICY, 0, ACTOR)
    seen = await asyncio.gather(first.read(), second.read())
    assert {s.version for s in seen} == {1}
    barrier = asyncio.Barrier(2)

    async def attempt(repo: SettingsRepository, policy: TimePolicy, actor: str) -> StoredSettings | VersionConflict:
        await barrier.wait()
        try:
            return await repo.write(policy, 1, actor)
        except VersionConflict as conflict:
            return conflict

    results = await asyncio.gather(attempt(first, NEW_YORK, ACTOR), attempt(second, DEFAULT_POLICY, OTHER))

    winners = [r for r in results if isinstance(r, StoredSettings)]
    losers = [r for r in results if isinstance(r, VersionConflict)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0].current == winners[0]
    assert winners[0].version == 2
    assert await owner.fetchval("select count(*) from settings.settings_change where (new->>'version')::int = 2") == 1


# Criterion 4
async def test_given_a_stale_version_when_written_then_conflict_and_nothing_changes(
    repo: SettingsRepository, owner: asyncpg.Connection
) -> None:
    current = await repo.write(DEFAULT_POLICY, 0, ACTOR)

    with pytest.raises(VersionConflict) as conflict:
        await repo.write(NEW_YORK, 5, ACTOR)

    assert conflict.value.current == current
    assert await repo.read() == current
    assert await owner.fetchval("select count(*) from settings.settings_change") == 1


async def test_given_no_row_when_written_at_a_later_version_then_conflict_with_the_defaults(
    repo: SettingsRepository, owner: asyncpg.Connection
) -> None:
    with pytest.raises(VersionConflict) as conflict:
        await repo.write(NEW_YORK, 3, ACTOR)

    assert (conflict.value.current.policy, conflict.value.current.version) == (DEFAULT_POLICY, 0)
    assert await owner.fetchval("select count(*) from settings.schedule") == 0


# Criterion 5
async def test_given_a_failing_audit_trigger_when_written_then_the_write_is_rolled_back_with_an_error(
    repo: SettingsRepository, owner: asyncpg.Connection
) -> None:
    current = await repo.write(DEFAULT_POLICY, 0, ACTOR)
    await owner.execute(BREAK_AUDIT)

    with pytest.raises(DBAPIError):
        await repo.write(NEW_YORK, 1, ACTOR)

    assert await repo.read() == current
    assert await owner.fetchval("select count(*) from settings.settings_change") == 1


async def test_given_a_failing_audit_trigger_when_the_first_row_is_written_then_no_row_exists(
    repo: SettingsRepository, owner: asyncpg.Connection
) -> None:
    await owner.execute(BREAK_AUDIT)

    with pytest.raises(DBAPIError):
        await repo.write(NEW_YORK, 0, ACTOR)

    assert await owner.fetchval("select count(*) from settings.schedule") == 0


# Criterion 6
async def test_given_a_write_that_skips_a_version_when_executed_as_the_web_role_then_42501(
    repo: SettingsRepository, web_database: Database
) -> None:
    await repo.write(DEFAULT_POLICY, 0, ACTOR)

    with pytest.raises(DBAPIError) as refused:
        async with web_database.session() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE settings.schedule SET version = version + 2, updated_via = 'web', updated_by = :by "
                    "WHERE id = 1"
                ),
                {"by": f"web:{ACTOR}"},
            )

    assert getattr(refused.value.orig, "sqlstate", None) == "42501"
    assert (await repo.read()).version == 1


async def test_given_an_actor_outside_the_web_form_when_written_then_42501(repo: SettingsRepository) -> None:
    with pytest.raises(DBAPIError) as refused:
        await repo.write(NEW_YORK, 0, "not-a-digest")

    assert getattr(refused.value.orig, "sqlstate", None) == "42501"


# Criterion 8
async def test_given_an_injection_zone_when_written_then_the_database_check_refuses_it_and_nothing_changes(
    repo: SettingsRepository, owner: asyncpg.Connection
) -> None:
    current = await repo.write(DEFAULT_POLICY, 0, ACTOR)
    hostile = TimePolicy("'; drop table settings.schedule; --", *_times(DEFAULT_POLICY))

    with pytest.raises(DBAPIError):
        await repo.write(hostile, 1, ACTOR)

    assert await repo.read() == current
    assert await owner.fetchval("select to_regclass('settings.schedule') is not null")


# Criterion 9
async def test_given_failure_paths_with_the_canary_zone_when_logged_then_no_record_holds_the_zone(
    repo: SettingsRepository, owner: asyncpg.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    canary = TimePolicy(CANARY_ZONE, *_times(DEFAULT_POLICY))
    await repo.write(canary, 0, ACTOR)
    with pytest.raises(VersionConflict):
        await repo.write(canary, 0, ACTOR)
    await owner.execute(BREAK_AUDIT)
    with pytest.raises(DBAPIError):
        await repo.write(canary, 1, ACTOR)

    assert CANARY_ZONE not in "\n".join(r.getMessage() for r in caplog.records)
