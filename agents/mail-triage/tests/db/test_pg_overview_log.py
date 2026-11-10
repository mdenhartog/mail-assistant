"""U-quiet-hours-13: the overview log on a real PostgreSQL, and the overview across a zone change (AC-27)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.pg_conversation import ConversationStore
from app.db.pg_overview_log import PgOverviewLog
from app.db.pg_store import PgStore
from app.usecases.overview import OverviewService
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy
from schedule_policy.testing import make_policy
from tests.db.test_pg_store import add, outcome

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.core.alert_text import AlertMessage

DAY = date(2026, 11, 9)
SENT = datetime(2026, 11, 9, 17, 1, tzinfo=UTC)


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def log(sessions: async_sessionmaker) -> PgOverviewLog:
    return PgOverviewLog(sessions)


async def test_given_no_overview_ever_when_asked_for_the_last_settled_instant_then_it_is_none(
    log: PgOverviewLog,
) -> None:
    assert await log.last_settled_at() is None


async def test_given_two_settled_dates_when_asked_then_the_latest_instant_is_returned(log: PgOverviewLog) -> None:
    await log.mark_overview_sent(DAY, SENT)
    await log.mark_overview_sent(DAY + timedelta(days=1), SENT + timedelta(days=1))

    assert await log.last_settled_at() == SENT + timedelta(days=1)
    assert await log.overview_sent(DAY) is True
    assert await log.overview_sent(DAY + timedelta(days=2)) is False


async def test_given_a_date_settled_twice_when_marked_again_then_the_first_instant_stays(log: PgOverviewLog) -> None:
    await log.mark_overview_sent(DAY, SENT)

    await log.mark_overview_sent(DAY, SENT + timedelta(hours=3))

    assert await log.last_settled_at() == SENT


class Outbox:
    def __init__(self) -> None:
        self.messages: list[AlertMessage] = []

    async def send(self, message: AlertMessage) -> int:
        self.messages.append(message)
        return len(self.messages)


class Policies:
    def __init__(self, policy: TimePolicy) -> None:
        self.policy = policy

    async def current(self) -> TimePolicy:
        return self.policy


async def test_given_the_overview_sent_in_amsterdam_when_the_zone_becomes_new_york_then_the_next_loses_no_mail(
    engine: AsyncEngine, sessions: async_sessionmaker, log: PgOverviewLog
) -> None:
    store, outbox, policies = (
        PgStore(sessions, ConversationStore(sessions, lambda: SENT)),
        Outbox(),
        Policies(DEFAULT_POLICY),
    )
    clock = [SENT]
    service = OverviewService(store, log, outbox, now=lambda: clock[0], policies=policies)

    async def file(message_id: str, label: str, filed_at: datetime) -> None:
        await add(store, message_id, outcome(label))
        async with engine.begin() as connection:
            await connection.execute(
                text("update mail_item set created_at = :t where gmail_message_id = :m"),
                {"t": filed_at, "m": message_id},
            )

    await file("before", "Assistant/Finance", SENT - timedelta(hours=1))
    await service.send_overview()  # 18:01 in Amsterdam: the mail filed before
    await file("after", "Assistant/Newsletters", SENT + timedelta(minutes=20))
    policies.policy = make_policy(zone="America/New_York")
    clock[0] = datetime(2026, 11, 9, 23, 5, tzinfo=UTC)  # 18:05 in New York, the same local date
    await service.send_overview()
    clock[0] = datetime(2026, 11, 10, 23, 1, tzinfo=UTC)  # 18:01 in New York on the next date
    await service.send_overview()

    assert len(outbox.messages) == 2
    assert "Newsletters" not in outbox.messages[0].text
    assert "Finance: 1" in outbox.messages[0].text
    assert "Newsletters: 1" in outbox.messages[1].text
    assert await log.last_settled_at() == clock[0]


async def test_given_an_instant_in_another_offset_when_read_back_then_it_is_the_same_moment(log: PgOverviewLog) -> None:
    amsterdam = datetime(2026, 11, 9, 18, 1, tzinfo=ZoneInfo("Europe/Amsterdam"))

    await log.mark_overview_sent(DAY, amsterdam)

    assert await log.last_settled_at() == SENT
