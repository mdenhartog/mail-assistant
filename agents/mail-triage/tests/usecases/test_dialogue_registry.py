"""U-quiet-hours-07: the router as a registry of dialogue handlers (spec C-8, AC-3 to AC-7, AC-33; ADR-0026)."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import pytest

from app.usecases.dispatch import (
    SEEN_UPDATES_MAX,
    SETTINGS_TTL,
    USE_BUTTONS,
    CommandRouter,
    button_data,
)
from tests.usecases.test_dispatch import Rig, button, text

TOKEN = "123456:ABC-secret-token"  # noqa: S105 - a fake token for tests
CANARY = "Pacific/Kiritimati"


def registered(rig: Rig) -> CommandRouter:
    router = rig.router()
    router.register(rig.settings)
    return router


async def open_card(rig: Rig, router: CommandRouter) -> str:
    """Start the settings dialogue with ``/settings`` and return the nonce the card carries."""
    await router.handle(text("/settings"))
    return rig.settings.began[-1].nonce


# ---- criterion 1: starting a dialogue replaces the stored one and says what was dropped (AC-5) ---------------------


async def test_given_a_pending_snooze_question_when_settings_starts_then_it_is_replaced_and_text_is_the_answer() -> (
    None
):
    rig = Rig()
    router = registered(rig)
    await rig.conversations.start("snooze", "5", "hours", {}, None)
    rig.store.waiting = ("5", "snooze_hours")

    await router.handle(text("/settings"))
    await router.handle(text("18:00"))

    assert rig.chat.said == ["I dropped the question about alert 5."]
    current = await rig.conversations.current()
    assert current is not None
    assert current.kind == "settings"
    assert [conversation.kind for conversation in rig.settings.began] == ["settings"]
    assert [answer for _nonce, answer in rig.settings.texts] == ["18:00"]
    assert rig.snooze.calls == []
    assert rig.reply.calls == []


async def test_given_a_pending_settings_question_when_settings_starts_again_then_the_drop_is_told() -> None:
    rig = Rig()
    router = registered(rig)
    first = await open_card(rig, router)

    second = await open_card(rig, router)

    assert second != first
    assert rig.chat.said == ["I dropped the open settings question."]


async def test_given_no_pending_question_when_settings_starts_then_nothing_is_said_about_a_drop() -> None:
    rig = Rig()
    router = registered(rig)

    await router.handle(text("/settings@MailBot"))

    assert rig.chat.said == []
    assert len(rig.settings.began) == 1
    current = await rig.conversations.current()
    assert current is not None
    assert current.expires_at == rig.clock.now() + SETTINGS_TTL
    assert timedelta(minutes=15) == SETTINGS_TTL


async def test_given_a_command_and_awaited_text_when_a_slash_command_comes_then_the_command_wins() -> None:
    rig = Rig()
    router = registered(rig)
    rig.store.waiting = ("5", "reply_text")

    await router.handle(text("/settings"))

    assert rig.reply.calls == []  # not taken as the reply text
    assert len(rig.settings.began) == 1


# ---- criterion 4: replayed updates are handled once --------------------------------------------------------------


async def test_given_a_replayed_update_when_it_arrives_twice_then_it_is_handled_once() -> None:
    rig = Rig()
    router = registered(rig)

    await router.handle(text("/settings", update_id=900))
    await router.handle(text("/settings", update_id=900))

    assert len(rig.settings.began) == 1
    assert rig.chat.said == []  # the replay did not drop the card it had just opened


async def test_given_a_replayed_button_when_it_arrives_twice_then_it_is_handled_and_answered_once() -> None:
    rig = Rig()
    router = registered(rig)
    nonce = await open_card(rig, router)

    await router.handle(button(button_data("set", nonce, "overview_time"), update_id=901))
    await router.handle(button(button_data("set", nonce, "overview_time"), update_id=901))

    assert len(rig.settings.buttons) == 1
    assert rig.chat.acknowledged == ["cb1"]


async def test_given_more_updates_than_the_memory_holds_when_an_old_one_is_replayed_then_memory_stayed_bounded() -> (
    None
):
    rig = Rig()
    router = registered(rig)
    for update_id in range(1, SEEN_UPDATES_MAX + 11):
        await router.handle(text("hello", update_id=update_id))
    said = len(rig.chat.said)

    await router.handle(text("hello", update_id=SEEN_UPDATES_MAX + 10))  # recent: still remembered
    assert len(rig.chat.said) == said
    await router.handle(text("hello", update_id=1))  # the oldest were forgotten to keep the memory bounded

    assert len(rig.chat.said) == said + 1


# ---- criterion 6: every tap is answered --------------------------------------------------------------------------


@pytest.mark.parametrize("data", ["set:overview_time:" + "x" * 22, "cancel:" + "y" * 22, "undo:" + "z" * 22, "junk"])
async def test_given_a_settings_style_button_in_any_state_when_tapped_then_the_callback_is_answered(data: str) -> None:
    rig = Rig()
    router = registered(rig)

    await router.handle(button(data))  # no conversation at all, stale nonce, or junk

    assert rig.chat.acknowledged == ["cb1"]


async def test_given_no_settings_handler_when_a_settings_button_is_tapped_then_it_is_answered_and_nothing_else() -> (
    None
):
    rig = Rig()
    router = rig.router()

    await router.handle(button("set:overview_time:" + "x" * 22))

    assert rig.chat.acknowledged == ["cb1"]
    assert rig.chat.said == rig.chat.offered == rig.chat.edited == []


# ---- criterion 8: text without a pending question -----------------------------------------------------------------


async def test_given_text_and_no_pending_question_when_handled_then_marco_is_pointed_to_the_buttons() -> None:
    rig = Rig()
    router = registered(rig)

    await router.handle(text("19:30"))

    assert rig.chat.said == [USE_BUTTONS]
    assert rig.settings.texts == []


# ---- button grammar ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "argument", "expected"),
    [
        ("set", "overview_time", "set:overview_time:N"),
        ("set", "quiet_hours", "set:quiet_hours:N"),
        ("tz", "3", "tz:3:N"),
        ("cancel", None, "cancel:N"),
        ("undo", None, "undo:N"),
    ],
)
def test_given_a_settings_button_when_built_then_it_is_ascii_within_the_callback_limit_and_never_a_value(
    action: str, argument: str | None, expected: str
) -> None:
    nonce = "N" * 22
    data = button_data(action, nonce, argument)

    assert data == expected.replace("N", nonce)
    assert data.isascii()
    assert len(data.encode("ascii")) <= 64


@pytest.mark.parametrize(
    ("action", "argument", "nonce"),
    [
        ("set", "18:00", "N" * 22),  # a value, not a key
        ("set", "zone/Europe", "N" * 22),
        ("set", "x" * 60, "N" * 22),  # would exceed 64 bytes
        ("set", "été", "N" * 22),
        ("tz", "100", "N" * 22),  # an index, at most two digits
        ("tz", None, "N" * 22),  # an index is required
        ("cancel", "oops", "N" * 22),  # no argument allowed
        ("zap", None, "N" * 22),
        ("undo", None, "short"),
        ("undo", None, "N" * 22 + "é"),
    ],
)
def test_given_a_malformed_settings_button_when_built_then_it_is_refused(
    action: str, argument: str | None, nonce: str
) -> None:
    with pytest.raises(ValueError, match="button"):
        button_data(action, nonce, argument)


@pytest.mark.parametrize(
    "data",
    [
        "set:../etc:" + "x" * 22,
        "set:overview_time:short",
        "set:overview_time:" + "x" * 22 + ":extra",
        "tz:999:" + "x" * 22,
        "tz:a:" + "x" * 22,
        "cancel:" + "x" * 21,
        "undo:",
        "zap:x:" + "x" * 22,
        "start:",
        "start:../x",
    ],
)
async def test_given_malformed_settings_data_when_tapped_then_nothing_runs_and_the_callback_is_answered(
    data: str,
) -> None:
    rig = Rig()
    router = registered(rig)
    await open_card(rig, router)

    await router.handle(button(data))

    assert rig.settings.buttons == []
    assert rig.chat.acknowledged == ["cb1"]
    assert rig.chat.offered == rig.chat.edited == []


# ---- criterion 2: stale and foreign nonces do nothing except offer a fresh card (AC-4) ----------------------------


async def test_given_an_old_nonce_button_when_tapped_then_nothing_changes_and_a_fresh_card_is_offered() -> None:
    rig = Rig()
    router = registered(rig)
    old = await open_card(rig, router)
    await router.handle(text("/settings"))
    before = await rig.conversations.current()

    await router.handle(button(button_data("set", old, "overview_time")))

    assert rig.settings.buttons == []
    assert await rig.conversations.current() == before  # not even the nonce moved
    assert rig.chat.offered == [("That card is out of date.", "Show settings", "start:settings")]


async def test_given_a_settings_button_while_a_snooze_question_is_pending_when_tapped_then_the_question_stays() -> None:
    rig = Rig()
    router = registered(rig)
    await rig.conversations.start("snooze", "5", "hours", {}, None)
    before = await rig.conversations.current()

    await router.handle(button(button_data("set", "x" * 22, "zone")))

    assert await rig.conversations.current() == before
    assert rig.settings.buttons == []
    assert rig.chat.offered == [("That card is out of date.", "Show settings", "start:settings")]


async def test_given_the_offered_fresh_card_button_when_tapped_then_settings_starts_like_the_command() -> None:
    rig = Rig()
    router = registered(rig)
    await rig.conversations.start("reply", "7", "text", {}, None)

    await router.handle(button("start:settings"))

    assert rig.chat.said == ["I dropped the question about alert 7."]
    assert len(rig.settings.began) == 1
    assert rig.chat.acknowledged == ["cb1"]


async def test_given_a_start_button_for_an_unknown_dialogue_when_tapped_then_nothing_starts() -> None:
    rig = Rig()
    router = registered(rig)

    await router.handle(button("start:unknown"))

    assert rig.settings.began == []
    assert rig.chat.acknowledged == ["cb1"]


# ---- criterion 5: Cancel keeps the old value and writes nothing (AC-7) --------------------------------------------


async def test_given_a_question_when_cancel_is_tapped_then_nothing_is_written_and_the_question_is_closed() -> None:
    rig = Rig()
    router = registered(rig)
    nonce = await open_card(rig, router)

    await router.handle(button(button_data("cancel", nonce)))

    assert rig.settings.writes == []
    assert await rig.conversations.current() is None
    assert rig.chat.edited == [(9, "Cancelled. Nothing was changed.")]
    assert rig.chat.acknowledged == ["cb1"]


async def test_given_a_cancelled_question_when_text_arrives_then_it_is_not_a_settings_answer() -> None:
    rig = Rig()
    router = registered(rig)
    nonce = await open_card(rig, router)
    await router.handle(button(button_data("cancel", nonce)))

    await router.handle(text("18:00"))

    assert rig.settings.texts == []
    assert rig.chat.said[-1] == USE_BUTTONS


async def test_given_a_draft_cancel_button_when_tapped_then_it_still_reaches_the_reply_flow() -> None:
    rig = Rig()
    router = registered(rig)
    await open_card(rig, router)

    await router.handle(button("cancel:d1"))  # a draft id is not a nonce

    assert rig.reply.calls == [("cancel", "d1")]
    assert (await rig.conversations.current()) is not None  # the open settings question is untouched


# ---- criterion 9: an old snooze or reply button leaves a pending settings question intact -------------------------


@pytest.mark.parametrize("data", ["later:5", "reply:5", "edit:d1"])
async def test_given_a_pending_settings_question_when_a_snooze_or_reply_question_button_is_tapped_then_it_stays(
    data: str,
) -> None:
    rig = Rig()
    router = registered(rig)
    await open_card(rig, router)
    before = await rig.conversations.current()

    await router.handle(button(data))

    assert await rig.conversations.current() == before
    assert rig.reply.calls == []
    assert rig.store.waiting is None
    assert rig.chat.said == ["Finish or cancel the settings question first."]
    assert rig.chat.acknowledged == ["cb1"]


@pytest.mark.parametrize("data", ["stop:5", "send:d1:abcdef0123456789"])
async def test_given_a_pending_settings_question_when_a_button_that_asks_nothing_is_tapped_then_it_still_works(
    data: str,
) -> None:
    rig = Rig()
    router = registered(rig)
    await open_card(rig, router)
    before = await rig.conversations.current()

    await router.handle(button(data))

    assert await rig.conversations.current() == before
    assert rig.reply.calls or rig.snooze.calls


# ---- criterion 10: a double tap, or a tap and a text at once, lead to one write -----------------------------------


async def test_given_a_double_tap_when_handled_then_only_one_write_happens() -> None:
    rig = Rig()
    router = registered(rig)
    nonce = await open_card(rig, router)
    data = button_data("set", nonce, "overview_time")

    await router.handle(button(data))
    await router.handle(button(data))  # a second update with the same nonce, as a double tap sends

    assert rig.settings.writes == ["button:set:overview_time"]
    assert rig.chat.offered == [("That card is out of date.", "Show settings", "start:settings")]


async def test_given_a_tap_and_a_text_at_once_when_handled_then_only_one_write_happens() -> None:
    rig = Rig()
    router = registered(rig)
    nonce = await open_card(rig, router)

    await asyncio.gather(
        router.handle(button(button_data("set", nonce, "overview_time"))),
        router.handle(text("18:00")),
    )

    assert len(rig.settings.writes) == 1


async def test_given_two_texts_at_once_when_handled_then_only_one_is_the_answer() -> None:
    rig = Rig()
    router = registered(rig)
    await open_card(rig, router)

    await asyncio.gather(router.handle(text("18:00")), router.handle(text("19:00")))

    assert len(rig.settings.texts) == 1


# ---- criteria 7 and 8: settings questions expire after 15 minutes (AC-6) ------------------------------------------

EXPIRY_TABLE = [
    pytest.param(timedelta(minutes=14, seconds=59), True, id="14:59:59-used"),
    pytest.param(timedelta(minutes=15), False, id="15:00:00-expired"),
    pytest.param(timedelta(minutes=15, seconds=1), False, id="15:00:01-expired"),
]


@pytest.mark.parametrize(("elapsed", "used"), EXPIRY_TABLE)
async def test_given_the_expiry_table_when_a_button_is_tapped_then_it_is_used_only_before_fifteen_minutes(
    elapsed: timedelta, *, used: bool
) -> None:
    rig = Rig()
    router = registered(rig)
    nonce = await open_card(rig, router)
    rig.clock.advance(elapsed)

    await router.handle(button(button_data("set", nonce, "overview_time")))

    assert rig.chat.acknowledged == ["cb1"]
    if used:
        assert rig.settings.writes == ["button:set:overview_time"]
        assert rig.chat.edited == rig.chat.offered == []
    else:
        assert rig.settings.writes == []
        assert rig.chat.edited == [(9, "Expired")]  # the old message loses its buttons
        assert rig.chat.offered == [("That question expired. Nothing was changed.", "Start again", "start:settings")]


@pytest.mark.parametrize(("elapsed", "used"), EXPIRY_TABLE)
async def test_given_the_expiry_table_when_text_arrives_then_it_is_an_answer_only_before_fifteen_minutes(
    elapsed: timedelta, *, used: bool
) -> None:
    rig = Rig()
    router = registered(rig)
    await open_card(rig, router)
    rig.clock.advance(elapsed)

    await router.handle(text("18:00"))

    if used:
        assert [answer for _nonce, answer in rig.settings.texts] == ["18:00"]
        assert rig.chat.said == []
    else:
        assert rig.settings.texts == []
        assert rig.chat.said == [USE_BUTTONS]  # the usual answer, never a settings answer
        assert rig.chat.edited == []


async def test_given_an_expired_cancel_button_when_tapped_then_it_only_says_expired() -> None:
    rig = Rig()
    router = registered(rig)
    nonce = await open_card(rig, router)
    rig.clock.advance(timedelta(minutes=20))

    await router.handle(button(button_data("cancel", nonce)))

    assert rig.chat.edited == [(9, "Expired")]
    assert rig.settings.writes == []


# ---- criterion 12: logs (AC-33) ----------------------------------------------------------------------------------


async def test_given_rejections_when_logged_then_no_token_nonce_answer_or_zone_appears(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    rig = Rig()
    router = registered(rig)
    nonce = await open_card(rig, router)
    stale = button_data("set", "x" * 22, "zone")

    await router.handle(button(stale))  # a stale nonce
    await router.handle(text(f"{CANARY} {TOKEN}"))  # an answer that carries the canary zone and a token
    await router.handle(button(button_data("set", nonce, "zone")))  # the nonce the answer just rotated away
    rig.clock.advance(timedelta(minutes=16))
    await router.handle(button(button_data("undo", rig.settings.texts[-1][0])))  # an expired question

    assert caplog.records, "rejections are logged by reason only, so this check is not vacuous"
    for needle in (CANARY, TOKEN, nonce, stale, "x" * 22):
        assert needle not in caplog.text


async def test_given_a_failing_handler_when_logged_then_the_error_reaches_the_caller_and_no_value_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    rig = Rig()
    router = registered(rig)
    await open_card(rig, router)

    async def failing(*_args: object) -> None:
        raise RuntimeError("store down")

    rig.settings.on_text = failing  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="store down"):
        await router.handle(text(f"{CANARY} {TOKEN}"))

    assert CANARY not in caplog.text
    assert TOKEN not in caplog.text
