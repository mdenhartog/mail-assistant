"""U-quiet-hours-16d (RT-5): the id of the last handled update is stored, so a redelivered update is not read again."""

from __future__ import annotations

import pytest

from app.usecases.dispatch import CommandRouter
from schedule_policy.testing import make_policy
from tests.usecases.fakes_dialogue import FakeUpdateCursor
from tests.usecases.test_dispatch import button, text
from tests.usecases.test_settings_dialog import Bot, FakeSettingsStore


async def test_given_a_start_time_answered_when_the_agent_restarts_and_it_is_redelivered_then_nothing_is_sent() -> None:
    bot = Bot(FakeSettingsStore(make_policy()))
    await bot.settings()
    await bot.tap("Change quiet hours")
    start_answer = text("22:00", update_id=777)
    await bot.router.handle(start_answer)
    assert bot.last.text.startswith("Quiet hours, step 2 of 2")
    assert bot.rig.cursor.value == 777

    restarted = CommandRouter(
        bot.rig.reply, bot.rig.snooze, bot.rig.store, bot.chat, bot.rig.conversations, bot.rig.cursor
    )
    restarted.register(bot.dialog)
    sent_before = len(bot.chat.sent)
    said_before = list(bot.chat.said)
    await restarted.handle(start_answer)

    assert len(bot.chat.sent) == sent_before
    assert bot.chat.said == said_before


async def test_given_a_stored_id_when_an_older_update_arrives_then_it_is_ignored() -> None:
    bot = Bot(FakeSettingsStore(make_policy()))
    bot.rig.cursor.value = 500
    bot.router = bot.rig.router()
    bot.router.register(bot.dialog)

    await bot.router.handle(text("/settings", update_id=500))
    await bot.router.handle(text("/settings", update_id=499))

    assert bot.chat.sent == []
    assert bot.rig.cursor.advances == []


async def test_given_an_update_when_it_is_handled_then_its_id_is_stored() -> None:
    bot = Bot(FakeSettingsStore(make_policy()))

    await bot.router.handle(text("/settings", update_id=41))

    assert bot.rig.cursor.advances == [41]


async def test_given_a_handling_step_that_fails_then_the_stored_id_stays_and_a_retry_is_handled() -> None:
    bot = Bot(FakeSettingsStore(make_policy()))
    bot.rig.cursor.value = 40
    broken = bot.chat.answer_callback

    async def fail(_callback_id: str) -> None:
        raise RuntimeError("boom")

    bot.chat.answer_callback = fail  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await bot.router.handle(button("start:settings", update_id=41))
    assert bot.rig.cursor.value == 40
    assert bot.rig.cursor.advances == []

    bot.chat.answer_callback = broken  # type: ignore[method-assign]
    await bot.router.handle(button("start:settings", update_id=41))

    assert bot.rig.cursor.value == 41
    assert len(bot.chat.sent) == 1  # the retry was handled, not mistaken for a replay


async def test_given_no_stored_id_when_the_first_update_arrives_then_it_is_handled() -> None:
    cursor = FakeUpdateCursor(None)
    bot = Bot(FakeSettingsStore(make_policy()))
    bot.rig.cursor = cursor
    bot.router = bot.rig.router()
    bot.router.register(bot.dialog)

    await bot.router.handle(text("/settings", update_id=1))

    assert len(bot.chat.sent) == 1
