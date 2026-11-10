"""U-quiet-hours-06a: the single conversation row (ADR-0026, spec C-8)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.alert_state import AlertState
from app.db.pg_conversation import NO_EXPIRY, ConversationStore
from app.db.pg_store import PgStore
from app.usecases.dispatch import CommandRouter, button_data
from app.usecases.snooze import SnoozeService
from tests.db.test_pg_store import add, outcome
from tests.usecases.fakes_dialogue import FakeSettings, FakeUpdateCursor
from tests.usecases.fakes_policy import FakePolicySource
from tests.usecases.test_dispatch import FakeChat, FakeReply, FakeSnooze
from tests.usecases.test_dispatch import button as press
from tests.usecases.test_dispatch import text as typed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def _pg_store(bind: AsyncEngine | async_sessionmaker[AsyncSession]) -> PgStore:
    sessions = bind if isinstance(bind, async_sessionmaker) else async_sessionmaker(bind, expire_on_commit=False)
    return PgStore(sessions, ConversationStore(sessions, Clock()))


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


async def test_given_a_set_awaiting_when_stored_then_the_conversation_row_holds_it_and_the_alert_has_no_such_column(
    engine: AsyncEngine,
) -> None:
    store = _pg_store(engine)
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()

    await store.set_awaiting(pending.alert_id, "snooze_hours")

    async with engine.connect() as connection:
        row = (await connection.execute(text("select kind, target, step from conversation"))).one()
        columns = (
            (
                await connection.execute(
                    text("select column_name from information_schema.columns where table_name = 'alert'")
                )
            )
            .scalars()
            .all()
        )
    assert tuple(row) == ("snooze", pending.alert_id, "hours")
    assert "awaiting_input" not in columns
    assert await store.awaiting() == (pending.alert_id, "snooze_hours")


async def test_given_a_snooze_question_when_a_reply_question_starts_for_another_alert_then_only_the_reply_is_awaited(
    engine: AsyncEngine,
) -> None:
    store = _pg_store(engine)
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    await add(store, "m2", outcome(alert=AlertState.OPEN))
    first, second = await store.unsent()

    await store.set_awaiting(first.alert_id, "snooze_hours")
    await store.set_awaiting(second.alert_id, "reply_text")
    await store.set_awaiting(first.alert_id, None)  # clearing an alert that is not the pending one changes nothing

    assert await store.awaiting() == (second.alert_id, "reply_text")


async def test_given_the_real_store_when_a_snooze_is_asked_and_answered_then_the_alert_is_snoozed_and_nothing_awaited(
    engine: AsyncEngine,
    conversations: ConversationStore,
) -> None:
    store = _pg_store(engine)
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    chat = FakeChat()
    snooze = SnoozeService(store, chat, lambda: NOW, FakePolicySource())
    router = CommandRouter(FakeReply(), snooze, store, chat, conversations, FakeUpdateCursor())

    await router.handle(press(f"later:{pending.alert_id}"))
    await router.handle(typed("3"))

    assert await store.state_of(pending.alert_id) is AlertState.SNOOZED
    assert await store.awaiting() is None


async def test_given_the_real_store_when_reply_replaces_a_pending_snooze_then_the_next_text_is_the_reply(
    engine: AsyncEngine,
    conversations: ConversationStore,
) -> None:
    store = _pg_store(engine)
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    chat, reply = FakeChat(), FakeReply()
    snooze = SnoozeService(store, chat, lambda: NOW, FakePolicySource())
    router = CommandRouter(reply, snooze, store, chat, conversations, FakeUpdateCursor())

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
    await add(_pg_store(sessions), "m1", outcome(alert=AlertState.OPEN))
    [pending] = await _pg_store(sessions).unsent()
    await _pg_store(sessions).set_awaiting(pending.alert_id, "reply_text")

    assert await _pg_store(sessions).awaiting() == (pending.alert_id, "reply_text")


async def _settings_rig(
    engine: AsyncEngine, conversations: ConversationStore
) -> tuple[CommandRouter, FakeSettings, FakeChat]:
    chat, settings = FakeChat(), FakeSettings()
    router = CommandRouter(FakeReply(), FakeSnooze(), _pg_store(engine), chat, conversations, FakeUpdateCursor())
    router.register(settings)
    await router.handle(typed("/settings"))
    return router, settings, chat


@pytest.mark.parametrize(
    ("elapsed", "used"),
    [
        (timedelta(minutes=14, seconds=59), True),
        (timedelta(minutes=15), False),
        (timedelta(minutes=15, seconds=1), False),
    ],
)
async def test_given_the_real_store_when_a_settings_button_is_tapped_around_the_limit_then_only_before_it_counts(
    engine: AsyncEngine, conversations: ConversationStore, clock: Clock, elapsed: timedelta, *, used: bool
) -> None:
    router, settings, chat = await _settings_rig(engine, conversations)
    clock.now = NOW + elapsed

    await router.handle(press(button_data("set", settings.began[0].nonce, "overview_time")))

    assert bool(settings.buttons) is used
    assert bool(chat.edited) is not used


async def test_given_the_real_store_when_the_same_button_is_tapped_twice_at_once_then_only_one_tap_reaches_the_handler(
    engine: AsyncEngine, conversations: ConversationStore
) -> None:
    router, settings, _chat = await _settings_rig(engine, conversations)
    data = button_data("set", settings.began[0].nonce, "quiet_hours")

    await asyncio.gather(router.handle(press(data)), router.handle(press(data)))

    assert settings.writes == ["button:set:quiet_hours"]  # the atomic advance gave the turn to exactly one update


async def test_given_the_real_store_when_a_tap_and_a_text_race_then_no_turn_of_the_conversation_is_used_twice(
    engine: AsyncEngine, conversations: ConversationStore
) -> None:
    router, settings, _chat = await _settings_rig(engine, conversations)
    data = button_data("set", settings.began[0].nonce, "quiet_hours")

    await asyncio.gather(router.handle(press(data)), router.handle(typed("22:00")))

    nonces = [nonce for nonce, *_rest in [*settings.buttons, *settings.texts]]
    assert 1 <= len(nonces) == len(set(nonces))  # a text has no nonce: it answers whichever step is open when it lands
