"""U-quiet-hours-05: the settings store against a real PostgreSQL (ADR-0025; AC-13, AC-21, AC-29, AC-30, AC-33, AC-36)."""

from __future__ import annotations

import asyncio
from datetime import time
from typing import TYPE_CHECKING

import pytest
from schedule_policy.policy import validate
from schedule_policy.testing import make_policy
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.pg_settings_store import PgSettingsStore
from app.db.repos import PolicyRefused, StoredSettings, VersionConflict

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from schedule_policy.policy import TimePolicy


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgSettingsStore:
    return PgSettingsStore(async_sessionmaker(engine, expire_on_commit=False))


async def test_given_no_row_when_read_then_none_and_when_written_with_version_0_then_version_1(
    store: PgSettingsStore,
) -> None:
    assert await store.read() is None

    policy = make_policy(zone="America/New_York", quiet_start=time(22, 30))
    written = await store.write(policy, 0, "telegram", "u1")

    assert written.version == 1
    assert (written.updated_via, written.updated_by) == ("telegram", "u1")
    assert await store.read() == written
    assert written.policy == policy


async def _audit_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return (await connection.execute(text("select count(*) from settings.settings_change"))).scalar_one()


async def test_given_two_sessions_that_read_the_same_version_when_both_write_then_one_wins_and_one_audit_is_added(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    await store.write(make_policy(), 0, "web", "seed")
    barrier = asyncio.Barrier(2)

    async def writer(quiet_start: time, by: str) -> object:
        seen = await store.read()
        assert seen is not None
        await barrier.wait()  # both have read version 1; neither has written yet
        try:
            return await store.write(make_policy(quiet_start=quiet_start), seen.version, "telegram", by)
        except VersionConflict as conflict:
            return conflict

    outcomes = await asyncio.gather(writer(time(22, 0), "a"), writer(time(21, 0), "b"))

    winners = [o for o in outcomes if isinstance(o, StoredSettings)]
    losers = [o for o in outcomes if isinstance(o, VersionConflict)]
    assert (len(winners), len(losers)) == (1, 1)
    stored = await store.read()
    assert stored == winners[0]
    assert stored.version == 2
    assert validate(stored.policy) == []
    assert await _audit_count(engine) == 2  # the seed and the winner; the loser left nothing


class _NoDatabase:
    """A session factory that fails the test when anything asks it for a session."""

    def __call__(self) -> object:
        raise AssertionError("the database was touched")

    def begin(self) -> object:
        raise AssertionError("the database was touched")


@pytest.mark.parametrize(
    ("policy", "rule"),
    [
        (make_policy(zone="Mars/Olympus"), "zone_unknown"),
        (make_policy(quiet_start=time(22, 0), quiet_end=time(11, 0), remind_at=time(12, 0)), "quiet_window_length"),
        (make_policy(overview_at=time(23, 30)), "overview_in_quiet_hours"),
    ],
)
async def test_given_an_invalid_policy_when_written_then_refused_before_the_database(
    policy: TimePolicy, rule: str
) -> None:
    store = PgSettingsStore(_NoDatabase())  # type: ignore[arg-type]

    with pytest.raises(PolicyRefused) as refused:
        await store.write(policy, 0, "telegram", "u1")

    assert [problem.rule for problem in refused.value.problems] == [rule]


async def test_given_a_stored_row_when_an_invalid_policy_is_written_then_the_row_and_audit_stay(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")

    with pytest.raises(PolicyRefused):
        await store.write(make_policy(zone="Mars/Olympus"), first.version, "telegram", "u1")

    assert await store.read() == first
    assert await _audit_count(engine) == 1


async def test_given_writes_when_they_commit_then_each_adds_exactly_one_audit_record(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")
    second = await store.write(make_policy(quiet_start=time(22, 0)), first.version, "telegram", "u2")

    async with engine.connect() as connection:
        rows = (
            await connection.execute(text('select via, by, old, new from settings.settings_change order by (new->>\'version\')::int'))
        ).all()
    assert [(row.via, row.by) for row in rows] == [("web", "u1"), ("telegram", "u2")]
    assert rows[0].old is None
    assert rows[1].old["version"] == first.version
    assert rows[1].old["quiet_start"] == 23 * 60
    assert rows[1].new["version"] == second.version
    assert rows[1].new["quiet_start"] == 22 * 60
