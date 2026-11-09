"""U-quiet-hours-11: the confirmation with the full picture, and Undo (C-7, C-8; AC-20, AC-21, AC-33; T-4)."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

import pytest

from app.db.repos import PolicyRefused, SettingsStoreFailure
from app.usecases.dispatch import button_data
from schedule_policy.policy import validate
from schedule_policy.testing import make_policy
from tests.usecases.test_dispatch import button, text
from tests.usecases.test_settings_dialog import USER, Bot, FakeSettingsStore, bot_with

if TYPE_CHECKING:
    from app.core.alert_text import AlertMessage

CANARY = "Pacific/Kiritimati"
UNDO_TTL = timedelta(hours=24)


def utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


EVENING = utc("2026-11-09T22:05")  # 23:05 in Amsterdam (UTC+1), 17:05 in New York (UTC-5), 03:35 in Kolkata (next day)


def lines(message: AlertMessage) -> list[str]:
    return message.text.splitlines()


async def change_zone(bot: Bot, place: str, now: datetime = EVENING) -> None:
    bot.rig.clock.set(now)
    await bot.settings()
    await bot.tap("Change time zone")
    await bot.type(place)


async def change_quiet_hours(bot: Bot, start: str, end: str, now: datetime = EVENING) -> None:
    bot.rig.clock.set(now)
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type(start)
    await bot.type(end)


# ---- criterion 1: the full picture after a zone change (AC-20) ------------------------------------------------------


async def test_given_a_zone_change_to_new_york_when_confirmed_then_offset_both_times_both_quiet_hours_and_overview() -> (
    None
):
    bot = bot_with(make_policy())

    await change_zone(bot, "New York")

    assert lines(bot.last) == [
        "Saved.",
        "Time zone: America/New_York (UTC-5)",
        "It is now 17:05 there, 23:05 in Amsterdam.",
        "Quiet hours: 23:00 to 07:00 New York time (05:00 to 13:00 Amsterdam time)",
        "Daily overview: 18:00",
        "Remind-me-later default: 09:00",
        "Next overview: today 18:00",
    ]


async def test_given_the_overview_time_has_passed_there_when_confirmed_then_the_next_overview_is_tomorrow() -> None:
    bot = bot_with(make_policy(overview_at=time(16, 0)))

    await change_zone(bot, "New York")  # 17:05 there, the overview of 16:00 has gone

    assert "Next overview: tomorrow 16:00" in lines(bot.last)


async def test_given_a_zone_change_when_confirmed_then_one_undo_button_bound_to_a_long_lived_undo_conversation() -> None:
    bot = bot_with(make_policy())

    await change_zone(bot, "New York")

    current = await bot.rig.conversations.current()
    assert current is not None
    assert (current.kind, current.step, current.partial) == ("settings", "undo", {"version": 2})
    assert current.expires_at == EVENING + UNDO_TTL
    undo = [b for b in bot.last.buttons if b.label == "Undo"]
    assert [b.data for b in undo] == [button_data("undo", current.nonce)]


async def test_given_a_store_failure_when_the_zone_is_saved_then_no_confirmation_is_sent() -> None:
    bot = bot_with(make_policy())
    bot.store.write_error = SettingsStoreFailure("OperationalError", "08006")

    await change_zone(bot, "New York")

    assert "Undo" not in bot.labels()
    assert "Saved." not in bot.last.text


# ---- criterion 2: the next clock change within 14 days (AC-20) -------------------------------------------------------


async def test_given_a_clock_change_within_14_days_when_confirmed_then_its_date_is_mentioned() -> None:
    bot = bot_with(make_policy())

    await change_zone(bot, "New York", now=utc("2026-10-28T22:05"))

    assert lines(bot.last)[-1] == "Next clock change: 2026-11-01 at 02:00 (UTC-4 to UTC-5)"


async def test_given_no_clock_change_within_14_days_when_confirmed_then_none_is_mentioned() -> None:
    bot = bot_with(make_policy())

    await change_zone(bot, "New York")  # the next one in New York is in March

    assert "clock change" not in bot.last.text


@pytest.mark.parametrize(
    ("now", "mentioned"),
    [
        (utc("2026-10-18T06:00"), True),  # the change is at 2026-11-01 06:00 UTC: exactly 14 days ahead
        (utc("2026-10-18T05:59"), False),  # one minute more than 14 days
        (utc("2026-11-01T06:00"), False),  # at the change itself: it has happened
    ],
)
async def test_given_a_clock_change_at_the_edge_of_14_days_when_confirmed_then_14_days_is_included(
    now: datetime, *, mentioned: bool
) -> None:
    bot = bot_with(make_policy())

    await change_zone(bot, "New York", now=now)

    assert ("Next clock change:" in bot.last.text) is mentioned


async def test_given_the_spring_forward_in_amsterdam_when_confirmed_then_the_gap_is_dated_and_labelled() -> None:
    bot = bot_with(make_policy())

    await change_quiet_hours(bot, "22:00", "06:00", now=utc("2027-03-20T12:00"))

    assert lines(bot.last)[-1] == "Next clock change: 2027-03-28 at 02:00 (UTC+1 to UTC+2)"


# ---- criterion 5: a change that is not a zone change (AC-20) ---------------------------------------------------------


async def test_given_a_quiet_hours_change_when_confirmed_then_hours_and_times_are_shown_without_a_zone_comparison() -> (
    None
):
    bot = bot_with(make_policy())

    await change_quiet_hours(bot, "22:00", "06:00")

    assert lines(bot.last) == [
        "Saved.",
        "Time zone: Europe/Amsterdam (UTC+1)",
        "Quiet hours: 22:00 to 06:00",
        "Daily overview: 18:00",
        "Remind-me-later default: 09:00",
        "Next overview: tomorrow 18:00",
    ]
    assert [b.label for b in bot.last.buttons] == ["Undo", "Show settings"]


async def test_given_the_same_zone_typed_again_when_confirmed_then_it_is_not_a_zone_comparison() -> None:
    bot = bot_with(make_policy())

    await change_zone(bot, "Amsterdam")

    assert "there" not in bot.last.text
    assert "Amsterdam time" not in bot.last.text


@pytest.mark.parametrize(
    ("label", "answer", "expected"),
    [
        ("Change daily overview", "19:30", "Daily overview: 19:30"),
        ("Change remind-me-later default", "10:15", "Remind-me-later default: 10:15"),
    ],
)
async def test_given_a_single_time_change_when_confirmed_then_the_full_picture_has_the_new_value(
    label: str, answer: str, expected: str
) -> None:
    bot = bot_with(make_policy())
    bot.rig.clock.set(EVENING)
    await bot.settings()
    await bot.tap(label)

    await bot.type(answer)

    assert expected in lines(bot.last)
    assert lines(bot.last)[0] == "Saved."
    assert "Undo" in bot.labels()


async def test_given_the_one_tap_move_when_taken_then_the_confirmation_shows_the_moved_overview() -> None:
    bot = bot_with(make_policy(overview_at=time(18, 0), remind_at=time(9, 0)))
    bot.rig.clock.set(EVENING)
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type("17:00")
    await bot.type("03:00")

    await bot.tap("Move to 03:00 and save")

    assert lines(bot.last)[:4] == [
        "Saved.",
        "Time zone: Europe/Amsterdam (UTC+1)",
        "Quiet hours: 17:00 to 03:00",
        "Daily overview: 03:00",
    ]
    assert "Undo" in bot.labels()


async def test_given_no_stored_row_when_the_zone_is_saved_then_the_comparison_is_with_the_default_zone() -> None:
    bot = bot_with(None)

    await change_zone(bot, "New York")

    assert "It is now 17:05 there, 23:05 in Amsterdam." in lines(bot.last)


# ---- criterion 6: half-hour and 45-minute offsets (AC-20) ------------------------------------------------------------


async def test_given_asia_kolkata_when_confirmed_then_the_offset_is_labelled_utc_plus_5_30() -> None:
    bot = bot_with(make_policy())

    await change_zone(bot, "Mumbai")

    assert lines(bot.last)[:4] == [
        "Saved.",
        "Time zone: Asia/Kolkata (UTC+5:30)",
        "It is now 03:35 there, 23:05 in Amsterdam.",
        "Quiet hours: 23:00 to 07:00 Kolkata time (18:30 to 02:30 Amsterdam time)",
    ]
    assert "clock change" not in bot.last.text


async def test_given_asia_kathmandu_when_confirmed_then_the_offset_is_labelled_utc_plus_5_45() -> None:
    bot = bot_with(make_policy())

    await change_zone(bot, "Kathmandu")

    assert "Time zone: Asia/Kathmandu (UTC+5:45)" in lines(bot.last)


# ---- criterion 3: Undo with an unchanged row (AC-21) -----------------------------------------------------------------


async def test_given_undo_and_an_unchanged_row_when_tapped_then_the_previous_values_return_with_a_new_confirmation() -> (
    None
):
    before = make_policy()
    bot = bot_with(before)
    await change_zone(bot, "New York")

    await bot.tap("Undo")

    assert bot.store.undos == [(2, "telegram", str(USER))]
    assert bot.store.row is not None
    assert (bot.store.row.policy, bot.store.row.version) == (before, 3)
    assert lines(bot.last) == [
        "Undone. The previous values are back.",
        "Time zone: Europe/Amsterdam (UTC+1)",
        "It is now 23:05 there, 17:05 in New York.",
        "Quiet hours: 23:00 to 07:00 Amsterdam time (17:00 to 01:00 New York time)",
        "Daily overview: 18:00",
        "Remind-me-later default: 09:00",
        "Next overview: tomorrow 18:00",
    ]
    current = await bot.rig.conversations.current()
    assert current is not None
    assert (current.step, current.partial) == ("undo", {"version": 3})
    assert bot.last.buttons[0].data == button_data("undo", current.nonce)


async def test_given_an_undone_change_when_undone_again_then_the_change_is_back() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    await bot.tap("Undo")

    await bot.tap("Undo")

    assert bot.store.row is not None
    assert (bot.store.row.policy.zone, bot.store.row.version) == ("America/New_York", 4)


async def test_given_a_double_tap_on_undo_when_handled_then_it_is_undone_once() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    undo = bot.button_labelled("Undo").data

    await bot.router.handle(button(undo))
    await bot.router.handle(button(undo))

    assert len(bot.store.undos) == 1


# ---- criterion 4: Undo after another change (AC-21) ------------------------------------------------------------------


async def test_given_another_change_since_when_undo_is_tapped_then_nothing_changes_and_the_bot_says_so() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    assert bot.store.row is not None
    bot.store.row = replace(bot.store.row, version=3, updated_via="web")  # someone else wrote meanwhile
    after_other = bot.store.row

    await bot.tap("Undo")

    assert bot.store.undos == []
    assert bot.store.row == after_other
    assert bot.last.text == "The settings changed since then, so I did not undo anything. Nothing was changed."
    assert bot.labels() == ["Show settings"]
    assert await bot.rig.conversations.current() is None


async def test_given_the_first_ever_change_when_undo_is_tapped_then_the_bot_says_there_is_nothing_to_undo() -> None:
    bot = bot_with(None)
    await change_zone(bot, "New York")

    await bot.tap("Undo")

    assert bot.store.undos == []
    assert bot.last.text == "There is nothing to undo: that was the first saved change. Nothing was changed."
    assert bot.store.row is not None
    assert bot.store.row.policy.zone == "America/New_York"


async def test_given_a_newer_dialogue_when_the_old_undo_is_tapped_then_nothing_changes_and_the_bot_says_so() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    old_undo = bot.button_labelled("Undo").data
    await bot.settings()  # a newer dialogue replaces the undo conversation

    await bot.router.handle(button(old_undo))

    assert bot.store.undos == []
    assert bot.chat.offered[-1] == (
        "The settings changed since then, so I did not undo anything. Nothing was changed.",
        "Show settings",
        "start:settings",
    )


async def test_given_a_store_failure_when_undo_is_tapped_then_nothing_changes_and_the_bot_says_so() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    bot.store.undo_error = SettingsStoreFailure("OperationalError", "08006")

    await bot.tap("Undo")

    assert bot.last.text == "I could not save that. Nothing was changed. Try again in a moment."
    assert bot.store.undos == []


async def test_given_previous_values_that_no_longer_pass_when_undo_is_tapped_then_the_bot_says_so() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    bot.store.undo_error = PolicyRefused(validate(make_policy(quiet_end=time(23, 0))))

    await bot.tap("Undo")

    assert bot.last.text == "I could not put the previous values back because they are no longer allowed. Nothing was changed."


# ---- criterion 7: Undo after 15 minutes or a restart (AC-21) ---------------------------------------------------------


@pytest.mark.parametrize("later", [timedelta(minutes=16), timedelta(hours=5), UNDO_TTL - timedelta(minutes=1)])
async def test_given_undo_tapped_long_after_the_change_when_the_row_is_unchanged_then_it_works(
    later: timedelta,
) -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    bot.rig.clock.advance(later)

    await bot.tap("Undo")

    assert len(bot.store.undos) == 1
    assert bot.last.text.startswith("Undone.")


async def test_given_an_agent_restart_when_undo_is_tapped_then_it_works_from_the_stored_conversation() -> None:
    first = bot_with(make_policy())
    await change_zone(first, "New York")
    undo = first.button_labelled("Undo").data
    first.rig.clock.advance(timedelta(minutes=20))

    restarted = Bot(first.store, first.rig)  # new router, dialogue and chat over the same stored conversation
    await restarted.router.handle(button(undo))

    assert len(first.store.undos) == 1
    assert restarted.last.text.startswith("Undone.")


async def test_given_an_agent_restart_and_another_change_when_undo_is_tapped_then_the_bot_says_so() -> None:
    first = bot_with(make_policy())
    await change_zone(first, "New York")
    undo = first.button_labelled("Undo").data
    assert first.store.row is not None
    first.store.row = replace(first.store.row, version=3)

    restarted = Bot(first.store, first.rig)
    await restarted.router.handle(button(undo))

    assert first.store.undos == []
    assert restarted.last.text.startswith("The settings changed since then")


async def test_given_undo_tapped_after_its_24_hours_when_handled_then_nothing_changes_and_the_bot_says_so() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    bot.rig.clock.advance(UNDO_TTL)

    await bot.router.handle(button(bot.button_labelled("Undo").data))

    assert bot.store.undos == []
    assert bot.chat.offered[-1][0].startswith("The settings changed since then")


# ---- the undo conversation next to the other flows -------------------------------------------------------------------


async def test_given_a_pending_undo_when_text_is_sent_then_it_is_not_taken_as_a_settings_answer() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    undo = bot.button_labelled("Undo").data

    await bot.router.handle(text("19:30"))

    assert bot.chat.said[-1] == "Use the buttons under an alert to reply, snooze or close it."
    assert bot.store.writes[-1][0].overview_at == time(18, 0)  # not read as an overview time
    await bot.router.handle(button(undo))  # the Undo button still works: the text did not rotate its nonce
    assert len(bot.store.undos) == 1


async def test_given_a_pending_undo_when_a_snooze_question_is_started_then_it_is_not_blocked_by_the_settings() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")

    await bot.router.handle(button("later:5"))

    assert "hours" in bot.chat.said[-1]
    assert "Finish or cancel" not in "".join(bot.chat.said)


async def test_given_a_pending_undo_when_settings_is_sent_then_no_dropped_question_is_announced() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    said = len(bot.chat.said)

    await bot.settings()

    assert bot.chat.said[said:] == []
    assert bot.labels()[0] == "Change quiet hours"


async def test_given_the_show_settings_button_when_tapped_then_the_card_is_shown() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")

    await bot.tap("Show settings")

    assert bot.labels()[0] == "Change quiet hours"


async def test_given_a_settings_button_with_the_undo_nonce_when_tapped_then_the_undo_offer_is_shown_again() -> None:
    bot = bot_with(make_policy())
    await change_zone(bot, "New York")
    current = await bot.rig.conversations.current()
    assert current is not None

    await bot.router.handle(button(button_data("set", current.nonce, "quiet")))

    assert [b.label for b in bot.last.buttons] == ["Undo", "Show settings"]
    assert bot.store.undos == []


# ---- logs (AC-33) ----------------------------------------------------------------------------------------------------


async def test_given_the_canary_zone_when_confirmed_undone_and_failing_then_no_zone_or_nonce_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    store = FakeSettingsStore(make_policy())
    bot = Bot(store)
    await change_zone(bot, "Kiritimati")
    assert store.row is not None
    assert store.row.policy.zone == CANARY
    nonces = [b.data.split(":")[-1] for b in bot.last.buttons if b.label == "Undo"]
    await bot.tap("Undo")  # the canary zone is the one undone
    store.undo_error = SettingsStoreFailure("OperationalError", "08006")
    nonces += [b.data.split(":")[-1] for b in bot.last.buttons if b.label == "Undo"]
    await bot.tap("Undo")
    store.undo_error = None
    await bot.settings()
    await bot.tap("Change time zone")
    await bot.type("Kiritimati")
    store.row = replace(store.row, version=store.row.version + 1)
    await bot.tap("Undo")

    assert all(nonces)
    assert CANARY not in caplog.text
    assert "Kiritimati" not in caplog.text
    for nonce in nonces:
        assert nonce not in caplog.text
