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
from app.db.repos import StoredSettings, VersionConflict

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


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
