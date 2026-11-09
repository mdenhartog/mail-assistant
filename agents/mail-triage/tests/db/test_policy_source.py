"""U-quiet-hours-08: PolicySource with fallback and notice (C-9; AC-1, AC-31, AC-32, AC-33; threat model T-6, T-9)."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.pg_policy_source import PgPolicySource
from app.db.pg_settings_store import PgSettingsStore
from app.usecases.policy_notice import PolicyNotice
from schedule_policy.policy import DEFAULT_POLICY
from schedule_policy.testing import make_policy

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class FakeNotifier:
    """Marco's Telegram chat: keeps every note sent."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def say(self, text: str) -> None:
        self.sent.append(text)


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgSettingsStore:
    return PgSettingsStore(async_sessionmaker(engine, expire_on_commit=False))


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def source(store: PgSettingsStore, notifier: FakeNotifier) -> PgPolicySource:
    return PgPolicySource(store, PolicyNotice(notifier))


async def test_given_a_stored_valid_row_when_read_then_its_policy_is_returned(
    store: PgSettingsStore, source: PgPolicySource, notifier: FakeNotifier
) -> None:
    stored = make_policy(zone="America/New_York", quiet_start=time(22, 30))
    await store.write(stored, 0, "telegram", "u1")

    assert await source.current() == stored
    assert notifier.sent == []


async def test_given_no_row_when_read_then_the_default_policy_and_no_notice(
    source: PgPolicySource, notifier: FakeNotifier
) -> None:
    assert await source.current() == DEFAULT_POLICY
    assert notifier.sent == []
