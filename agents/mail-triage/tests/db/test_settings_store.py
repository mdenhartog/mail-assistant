"""U-quiet-hours-05: the settings store against a real PostgreSQL (ADR-0025; AC-13, AC-21, AC-29, AC-30, AC-33, AC-36)."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

import pytest
from schedule_policy.testing import make_policy
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.pg_settings_store import PgSettingsStore

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
