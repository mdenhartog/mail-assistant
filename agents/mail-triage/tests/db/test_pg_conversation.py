"""U-quiet-hours-06a: the single conversation row (ADR-0026, spec C-8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.alert_state import AlertState
from app.db.pg_conversation import NO_EXPIRY, ConversationStore
from app.db.pg_store import PgStore
from app.usecases.dispatch import CommandRouter
from app.usecases.snooze import SnoozeService
from tests.db.test_pg_store import add, outcome
from tests.usecases.test_dispatch import FakeChat, FakeReply
from tests.usecases.test_dispatch import button as press
from tests.usecases.test_dispatch import text as typed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def conversations(engine: AsyncEngine, clock: Clock) -> ConversationStore:
    return ConversationStore(async_sessionmaker(engine, expire_on_commit=False), clock)


async def test_given_no_dialogue_when_one_starts_then_it_is_the_current_one_and_clear_removes_it(
    conversations: ConversationStore,
) -> None:
    assert await conversations.current() is None

    started = await conversations.start("snooze", "7", "hours", {}, None)

    current = await conversations.current()
    assert current == started
    assert current is not None
    assert (current.kind, current.target, current.step, current.partial) == ("snooze", "7", "hours", {})
    assert current.expires_at is None
    await conversations.clear()
    assert await conversations.current() is None


async def test_given_a_pending_snooze_when_a_reply_starts_then_only_the_reply_is_pending(
    conversations: ConversationStore, engine: AsyncEngine
) -> None:
    await conversations.start("snooze", "7", "hours", {}, None)

    await conversations.start("reply", "9", "text", {}, None)

    current = await conversations.current()
    assert current is not None
    assert (current.kind, current.target) == ("reply", "9")
    async with engine.connect() as connection:
        rows = (await connection.execute(text("select kind from conversation"))).all()
    assert [r[0] for r in rows] == ["reply"]


async def test_given_two_starts_when_compared_then_each_has_its_own_random_nonce(
    conversations: ConversationStore,
) -> None:
    first = await conversations.start("snooze", "7", "hours", {}, None)
    second = await conversations.start("snooze", "7", "hours", {}, None)

    assert first.nonce != second.nonce
    assert len(second.nonce) >= 16


async def test_given_a_pending_question_when_the_agent_restarts_then_it_is_still_pending(
    engine: AsyncEngine, clock: Clock
) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await ConversationStore(sessions, clock).start("reply", "9", "text", {}, None)

    after_restart = ConversationStore(sessions, clock)

    current = await after_restart.current()
    assert current is not None
    assert (current.kind, current.target, current.step) == ("reply", "9", "text")


async def test_given_a_ttl_when_the_expiry_passes_then_the_question_is_gone_at_the_boundary(
    conversations: ConversationStore, clock: Clock
) -> None:
    await conversations.start("settings", None, "start", {"k": "v"}, timedelta(minutes=15))

    clock.now = NOW + timedelta(minutes=15) - timedelta(seconds=1)
    assert await conversations.current() is not None
    clock.now = NOW + timedelta(minutes=15)
    assert await conversations.current() is None


async def test_given_no_ttl_when_a_long_time_passes_then_the_question_stays_pending(
    conversations: ConversationStore, clock: Clock, engine: AsyncEngine
) -> None:
    await conversations.start("snooze", "7", "hours", {}, None)

    clock.now = NOW + timedelta(days=3650)

    assert await conversations.current() is not None
    async with engine.connect() as connection:
        stored = (await connection.execute(text("select expires_at from conversation"))).scalar_one()
    assert stored == NO_EXPIRY


async def test_given_a_pending_dialogue_when_advanced_with_its_nonce_then_step_changes_and_the_nonce_rotates(
    conversations: ConversationStore,
) -> None:
    started = await conversations.start("settings", None, "start", {}, timedelta(minutes=15))

    advanced = await conversations.advance(started.nonce, "end", {"start": "23:00"})

    assert advanced is not None
    assert (advanced.step, advanced.partial) == ("end", {"start": "23:00"})
    assert advanced.nonce != started.nonce
    assert await conversations.current() == advanced
    assert await conversations.advance(started.nonce, "zone", {}) is None  # the old nonce is stale


async def test_given_an_expired_dialogue_when_advanced_then_nothing_changes(
    conversations: ConversationStore, clock: Clock
) -> None:
    started = await conversations.start("settings", None, "start", {}, timedelta(minutes=15))
    clock.now = NOW + timedelta(minutes=16)

    assert await conversations.advance(started.nonce, "end", {}) is None


async def test_given_a_set_awaiting_when_stored_then_the_conversation_row_holds_it_and_the_alert_column_stays_empty(
    engine: AsyncEngine,
) -> None:
    store = PgStore(async_sessionmaker(engine, expire_on_commit=False))
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()

    await store.set_awaiting(pending.alert_id, "snooze_hours")

    async with engine.connect() as connection:
        row = (await connection.execute(text("select kind, target, step from conversation"))).one()
        column = (await connection.execute(text("select awaiting_input from alert"))).scalar_one()
    assert tuple(row) == ("snooze", pending.alert_id, "hours")
    assert column is None
    assert await store.awaiting() == (pending.alert_id, "snooze_hours")


async def test_given_a_snooze_question_when_a_reply_question_starts_for_another_alert_then_only_the_reply_is_awaited(
    engine: AsyncEngine,
) -> None:
    store = PgStore(async_sessionmaker(engine, expire_on_commit=False))
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    await add(store, "m2", outcome(alert=AlertState.OPEN))
    first, second = await store.unsent()

    await store.set_awaiting(first.alert_id, "snooze_hours")
    await store.set_awaiting(second.alert_id, "reply_text")
    await store.set_awaiting(first.alert_id, None)  # clearing an alert that is not the pending one changes nothing

    assert await store.awaiting() == (second.alert_id, "reply_text")


async def test_given_the_real_store_when_a_snooze_is_asked_and_answered_then_the_alert_is_snoozed_and_nothing_awaited(
    engine: AsyncEngine, conversations: ConversationStore,
) -> None:
    store = PgStore(async_sessionmaker(engine, expire_on_commit=False))
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    chat = FakeChat()
    router = CommandRouter(FakeReply(), SnoozeService(store, chat, lambda: NOW), store, chat, conversations)

    await router.handle(press(f"later:{pending.alert_id}"))
    await router.handle(typed("3"))

    assert await store.state_of(pending.alert_id) is AlertState.SNOOZED
    assert await store.awaiting() is None


async def test_given_the_real_store_when_reply_replaces_a_pending_snooze_then_the_next_text_is_the_reply(
    engine: AsyncEngine, conversations: ConversationStore,
) -> None:
    store = PgStore(async_sessionmaker(engine, expire_on_commit=False))
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    chat, reply = FakeChat(), FakeReply()
    router = CommandRouter(reply, SnoozeService(store, chat, lambda: NOW), store, chat, conversations)

    await router.handle(press(f"later:{pending.alert_id}"))
    await router.handle(press(f"reply:{pending.alert_id}"))
    await router.handle(typed("Yes, tomorrow."))

    assert reply.calls == [("begin", pending.alert_id), ("start_reply", pending.alert_id, "Yes, tomorrow.")]
    assert await store.state_of(pending.alert_id) is AlertState.OPEN


async def test_given_no_dialogue_when_cleared_then_nothing_happens(conversations: ConversationStore) -> None:
    await conversations.clear()

    assert await conversations.current() is None


async def test_given_a_pending_question_when_the_store_is_rebuilt_then_awaiting_still_answers(
    engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await add(PgStore(sessions), "m1", outcome(alert=AlertState.OPEN))
    [pending] = await PgStore(sessions).unsent()
    await PgStore(sessions).set_awaiting(pending.alert_id, "reply_text")

    assert await PgStore(sessions).awaiting() == (pending.alert_id, "reply_text")
