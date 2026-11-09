"""U-quiet-hours-09 on a real PostgreSQL: the dialogue with the real settings store and conversation row (AC-11, AC-13, AC-29)."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.pg_conversation import ConversationStore
from app.db.pg_settings_store import PgSettingsStore
from app.usecases.dispatch import CommandRouter
from app.usecases.settings_dialog import SettingsDialog
from schedule_policy.testing import FakeClock, make_policy
from tests.usecases.test_dispatch import FakeReply, FakeSnooze, FakeStore, button
from tests.usecases.test_dispatch import text as typed
from tests.usecases.test_settings_dialog import RecordingChat

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.core.alert_text import Button

USER = 4242
CANARY = "Pacific/Kiritimati"


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@dataclass
class Rig:
    store: PgSettingsStore
    chat: RecordingChat
    router: CommandRouter

    def tap(self, label: str) -> Button:
        matches = [b for b in self.chat.sent[-1].buttons if b.label == label]
        assert len(matches) == 1, [b.label for b in self.chat.sent[-1].buttons]
        return matches[0]

    async def press(self, label: str) -> None:
        await self.router.handle(button(self.tap(label).data))

    async def say(self, answer: str) -> None:
        await self.router.handle(typed(answer))


@pytest.fixture
def rig(engine: AsyncEngine) -> Rig:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    chat = RecordingChat()
    store = PgSettingsStore(sessions)
    clock = FakeClock()
    conversations = ConversationStore(sessions, clock.now)
    router = CommandRouter(FakeReply(), FakeSnooze(), FakeStore(), chat, conversations)
    router.register(SettingsDialog(store, chat, conversations, USER, clock.now))
    return Rig(store, chat, router)


async def _audit_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return (await connection.execute(text("select count(*) from settings.settings_change"))).scalar_one()


async def test_given_no_row_when_quiet_hours_are_answered_then_one_row_and_one_audit_record_are_written(
    rig: Rig, engine: AsyncEngine
) -> None:
    await rig.router.handle(typed("/settings"))
    await rig.press("Change quiet hours")
    await rig.say("22:00")
    assert await rig.store.read() is None  # the start alone stores nothing
    await rig.say("06:00")

    stored = await rig.store.read()
    assert stored is not None
    assert (stored.version, stored.updated_via, stored.updated_by) == (1, "telegram", str(USER))
    assert stored.policy == make_policy(quiet_start=time(22, 0), quiet_end=time(6, 0))
    assert await _audit_count(engine) == 1


async def test_given_a_database_fault_between_the_steps_when_the_end_is_answered_then_the_row_stays_as_it_was(
    rig: Rig, engine: AsyncEngine
) -> None:
    seed = await rig.store.write(make_policy(zone=CANARY), 0, "web", "seed")
    await rig.router.handle(typed("/settings"))
    await rig.press("Change quiet hours")
    await rig.say("22:00")
    async with engine.begin() as connection:  # a real fault at write time: the database refuses every update
        await connection.execute(
            text(
                "create function settings.refuse() returns trigger language plpgsql as "
                "$$ begin raise exception 'refused for the test'; end $$"
            )
        )
        await connection.execute(
            text(
                "create trigger refuse before update on settings.schedule for each row execute function settings.refuse()"
            )
        )

    await rig.say("06:00")

    assert rig.chat.sent[-1].text == "I could not save that. Nothing was changed. Try again in a moment."
    assert await rig.store.read() == seed
    assert CANARY not in rig.chat.sent[-1].text


async def test_given_a_trapped_overview_when_the_move_is_taken_then_both_values_are_stored_in_one_audited_write(
    rig: Rig, engine: AsyncEngine
) -> None:
    await rig.store.write(make_policy(overview_at=time(18, 0)), 0, "web", "seed")
    await rig.router.handle(typed("/settings"))
    await rig.press("Change quiet hours")
    await rig.say("17:00")
    await rig.say("03:00")
    assert (await rig.store.read()).version == 1  # type: ignore[union-attr]  # the offer stored nothing

    await rig.press("Move to 03:00 and save")

    stored = await rig.store.read()
    assert stored is not None
    assert stored.policy == make_policy(quiet_start=time(17, 0), quiet_end=time(3, 0), overview_at=time(3, 0))
    assert stored.version == 2
    assert await _audit_count(engine) == 2  # the seed and ONE change


async def test_given_another_writer_between_card_and_answer_when_answered_then_the_other_value_survives(
    rig: Rig,
) -> None:
    await rig.store.write(make_policy(), 0, "web", "seed")
    await rig.router.handle(typed("/settings"))
    await rig.press("Change daily overview")
    await rig.store.write(make_policy(remind_at=time(8, 0)), 1, "web", "other")

    await rig.say("19:00")

    stored = await rig.store.read()
    assert stored is not None
    assert (stored.version, stored.policy.remind_at, stored.policy.overview_at) == (2, time(8, 0), time(18, 0))
    assert rig.chat.sent[-1].text.splitlines()[0].startswith("Your settings changed elsewhere.")
