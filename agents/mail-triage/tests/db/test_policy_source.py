"""U-quiet-hours-08: PolicySource with fallback and notice (C-9; AC-1, AC-31, AC-32, AC-33; threat model T-6, T-9)."""

from __future__ import annotations

import logging
from datetime import time
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
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


# Statements that make the stored row break a rule. The constraints of migration 0004 keep most of these out of a
# healthy database, so each case first lifts the constraint it needs (as an operator with owner rights could).
_CORRUPTIONS = {
    "unknown_zone": ["update settings.schedule set zone = 'Mars/Olympus'"],
    "window_of_13_hours": [
        "alter table settings.schedule drop constraint ck_schedule_window_length",
        "alter table settings.schedule drop constraint ck_schedule_overview_outside",
        "alter table settings.schedule drop constraint ck_schedule_remind_outside",
        "update settings.schedule set quiet_start = 22 * 60, quiet_end = 11 * 60",
    ],
    "overview_inside_the_window": [
        "alter table settings.schedule drop constraint ck_schedule_overview_outside",
        "update settings.schedule set overview_at = 23 * 60 + 30",
    ],
    "null_value": [
        "alter table settings.schedule alter column remind_at drop not null",
        "update settings.schedule set remind_at = null",
    ],
}
GOOD = make_policy(zone="America/New_York", quiet_start=time(22, 30), quiet_end=time(6, 30), overview_at=time(17, 15))


async def _corrupt(engine: AsyncEngine, case: str) -> None:
    async with engine.begin() as connection:
        for statement in _CORRUPTIONS[case]:
            await connection.execute(text(statement))


@pytest.mark.parametrize("case", list(_CORRUPTIONS))
@pytest.mark.parametrize("had_good_read", [False, True])
async def test_given_an_invalid_stored_row_when_read_then_last_good_or_default_one_notice_and_settings_invalid_logged(
    case: str,
    had_good_read: bool,  # noqa: FBT001
    store: PgSettingsStore,
    engine: AsyncEngine,
    source: PgPolicySource,
    notifier: FakeNotifier,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await store.write(GOOD, 0, "telegram", "u1")
    if had_good_read:
        assert await source.current() == GOOD
    await _corrupt(engine, case)

    first = await source.current()
    second = await source.current()

    expected = GOOD if had_good_read else DEFAULT_POLICY
    assert (first, second) == (expected, expected)
    assert len(notifier.sent) == 1
    assert expected.zone in notifier.sent[0]
    assert any("settings_invalid" in record.getMessage() for record in caplog.records)
    assert "Olympus" not in caplog.text
