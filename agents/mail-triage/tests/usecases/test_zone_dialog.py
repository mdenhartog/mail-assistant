"""U-quiet-hours-10: the time zone question: lookup, buttons, near miss, nothing found (C-6, AC-9, AC-14 to 19)."""

from __future__ import annotations

import logging
import re
from datetime import time
from typing import TYPE_CHECKING

import pytest

from app.db.repos import SettingsStoreFailure, StoredSettings
from app.usecases import settings_dialog
from schedule_policy import places
from schedule_policy.testing import make_policy
from tests.usecases.test_dispatch import button
from tests.usecases.test_settings_dialog import NOW, USER, Bot, bot_with

if TYPE_CHECKING:
    from datetime import datetime

CANARY = "Pacific/Kiritimati"
TZ_BUTTON = re.compile(r"tz:\d{1,2}:[A-Za-z0-9_-]{22}")


class LookupSpy:
    """Stands in for ``places.lookup`` in the dialogue and records every call; delegates to the real one."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, datetime]] = []

    def __call__(self, text: str, *, now: datetime) -> places.LookupResult:
        self.calls.append((text, now))
        return places.lookup(text, now=now)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> LookupSpy:
    recorder = LookupSpy()
    monkeypatch.setattr(settings_dialog, "lookup", recorder)
    return recorder


async def _at_zone_question(bot: Bot) -> None:
    await bot.settings()
    await bot.tap("Change time zone")


# ---- the question ----------------------------------------------------------------------------------------------------


async def test_given_the_time_zone_button_when_tapped_then_a_city_or_country_is_asked_with_cancel() -> None:
    bot = bot_with(make_policy())

    await _at_zone_question(bot)

    assert bot.last.text == "Time zone: type a city or a country, for example Paris or Japan."
    assert bot.labels() == ["Cancel"]


# ---- criterion 1: one hit stores it (AC-14) --------------------------------------------------------------------------


@pytest.mark.parametrize("answer", ["New York", "new york", "NEW YORK", "NYC"])
async def test_given_a_single_place_when_answered_then_its_zone_is_written(answer: str) -> None:
    bot = bot_with(make_policy(overview_at=time(17, 0)))
    await _at_zone_question(bot)

    await bot.type(answer)

    assert bot.store.writes == [
        (make_policy(overview_at=time(17, 0), zone="America/New_York"), 1, "telegram", str(USER))
    ]
    assert bot.last.text.splitlines()[0] == "Saved."
    assert "Time zone: America/New_York (UTC-5)" in bot.last.text.splitlines()


async def test_given_an_accented_place_when_answered_then_it_is_found_without_regard_to_accents() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type("Zürich")

    assert [w[0].zone for w in bot.store.writes] == ["Europe/Zurich"]


# ---- criterion 2: several hits show buttons (AC-15) ------------------------------------------------------------------


async def test_given_paris_when_answered_then_at_most_five_labelled_buttons_and_the_chosen_one_is_stored() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type("Paris")

    labels = bot.labels()
    assert labels[0] == "Paris, France (UTC+1)"
    assert labels[-1] == "Cancel"
    assert 2 <= len(labels) - 1 <= 5
    assert bot.store.writes == []
    await bot.tap("Paris, France (UTC+1)")
    assert [w[0].zone for w in bot.store.writes] == ["Europe/Paris"]
    assert bot.store.writes[0][1:] == (1, "telegram", str(USER))
    assert bot.last.text.splitlines()[0] == "Saved."


async def test_given_candidate_buttons_when_inspected_then_they_carry_an_index_and_a_nonce_never_a_zone() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type("Paris")

    zone_buttons = [b for b in bot.last.buttons if b.label != "Cancel"]
    assert all(TZ_BUTTON.fullmatch(b.data) for b in zone_buttons)
    assert all(len(b.data.encode()) <= 64 for b in bot.last.buttons)
    assert not any("Paris" in b.data or "Europe" in b.data for b in bot.last.buttons)
    assert [b.data.split(":")[1] for b in zone_buttons] == [str(i) for i in range(len(zone_buttons))]


async def test_given_candidate_buttons_when_the_user_types_another_place_then_a_new_lookup_replaces_them() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    await bot.type("Paris")

    await bot.type("Tokyo")

    assert [w[0].zone for w in bot.store.writes] == ["Asia/Tokyo"]


async def test_given_candidate_buttons_when_a_cancel_is_tapped_then_nothing_is_stored() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    await bot.type("Paris")

    await bot.tap("Cancel")

    assert bot.store.writes == []
    assert await bot.rig.conversations.current() is None


# ---- criterion 3: a near miss (AC-16) --------------------------------------------------------------------------------


async def test_given_a_near_miss_when_answered_then_did_you_mean_with_a_button_that_stores_the_suggestion() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type("Nwe York")

    assert bot.last.text.splitlines()[0] == "Did you mean New York?"
    assert bot.labels() == ["New York, United States (UTC-5)", "Cancel"]
    assert bot.store.writes == []
    await bot.tap("New York, United States (UTC-5)")
    assert [w[0].zone for w in bot.store.writes] == ["America/New_York"]


# ---- criterion 4: nothing found (AC-17) ------------------------------------------------------------------------------


async def test_given_nothing_found_when_answered_then_it_says_so_suggests_a_hint_and_keeps_cancel() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type("Xyzzyville")

    assert "I could not find a time zone for that." in bot.last.text
    assert "the nearest big city or the country" in bot.last.text
    assert "Xyzzyville" not in bot.last.text
    assert bot.labels() == ["Cancel"]
    assert bot.store.writes == []


async def test_given_nothing_found_when_a_place_is_typed_next_then_the_question_is_still_open() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    await bot.type("Xyzzyville")

    await bot.type("Berlin")

    assert [w[0].zone for w in bot.store.writes] == ["Europe/Berlin"]


# ---- criterion 5: a country (AC-18) ----------------------------------------------------------------------------------


@pytest.mark.parametrize(("answer", "city"), [("USA", "Chicago"), ("Australia", "Perth")])
async def test_given_a_large_country_when_answered_then_zone_buttons_with_city_names(answer: str, city: str) -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type(answer)

    labels = bot.labels()
    assert labels[-1] == "Cancel"
    assert any(label.startswith(f"{city}, ") for label in labels)
    assert 2 <= len(labels) - 1 <= 5
    assert bot.store.writes == []


# ---- criterion 6: hostile text (AC-9, T-3) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "../etc",
        "Europe/../etc",
        "'; DROP TABLE x;--",
        "x" * 65,
        "a" * 5000,
        "Paris\x00",
        "Paris\x1b[31m",
        "\U0001f600",
        "   ",
        "",
        "C:\\Windows",
        "Paris; rm -rf /",
    ],
)
async def test_given_hostile_text_when_answered_then_nothing_is_stored_and_lookup_is_never_called_with_it(
    answer: str, spy: LookupSpy
) -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type(answer)

    assert bot.store.writes == []
    assert spy.calls == []
    assert bot.labels() == ["Cancel"]
    assert "type a city or a country" in bot.last.text


async def test_given_a_text_of_exactly_64_characters_when_answered_then_lookup_is_called(spy: LookupSpy) -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    text = "a" * 64

    await bot.type(text)

    assert [call[0] for call in spy.calls] == [text]
    assert bot.store.writes == []


async def test_given_a_place_when_looked_up_then_the_injected_clock_moment_is_passed() -> None:
    spy_calls: list[datetime] = []

    def spy(text: str, *, now: datetime) -> places.LookupResult:
        spy_calls.append(now)
        return places.lookup(text, now=now)

    bot = bot_with(make_policy())
    bot.rig.clock.set(NOW)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings_dialog, "lookup", spy)
        await _at_zone_question(bot)
        await bot.type("Paris")

    assert spy_calls == [NOW]


# ---- criterion 7: a button outside the candidates --------------------------------------------------------------------


async def test_given_a_tz_button_with_an_index_outside_the_candidates_when_tapped_then_nothing_changes() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    await bot.type("Paris")
    nonce = bot.last.buttons[0].data.rsplit(":", 1)[1]

    await bot.router.handle(button(f"tz:9:{nonce}"))

    assert bot.store.writes == []
    assert bot.labels()[0] == "Paris, France (UTC+1)"  # the choices are offered again
    await bot.tap("Paris, France (UTC+1)")
    assert [w[0].zone for w in bot.store.writes] == ["Europe/Paris"]


async def test_given_candidate_buttons_when_repeated_then_the_choices_return_under_a_new_nonce() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    await bot.type("Paris")
    first = bot.last.buttons[0].data.rsplit(":", 1)[1]

    await bot.router.handle(button(f"tz:9:{first}"))

    assert bot.last.buttons[0].data.rsplit(":", 1)[1] != first
    assert bot.last.text.startswith("Tap one of the buttons below")
    await bot.router.handle(button(f"tz:0:{first}"))  # the old button is now stale
    assert bot.store.writes == []


async def test_given_a_tz_button_when_tapped_on_the_card_step_then_nothing_is_stored() -> None:
    bot = bot_with(make_policy())
    await bot.settings()
    nonce = bot.last.buttons[0].data.rsplit(":", 1)[1]

    await bot.router.handle(button(f"tz:0:{nonce}"))

    assert bot.store.writes == []
    assert bot.labels()[0] == "Change quiet hours"


async def test_given_a_tz_button_when_no_choices_exist_then_nothing_is_stored() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    current = await bot.rig.conversations.current()
    assert current is not None

    await bot.router.handle(button(f"tz:0:{current.nonce}"))

    assert bot.store.writes == []
    assert bot.last.text.startswith("Time zone: type a city or a country")


# ---- criterion 8: IANA names (AC-19, AC-33) --------------------------------------------------------------------------


async def test_given_a_listed_iana_name_when_typed_then_it_is_stored() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type("Europe/Paris")

    assert [w[0].zone for w in bot.store.writes] == ["Europe/Paris"]


async def test_given_an_unlisted_iana_name_when_typed_then_nothing_is_found_and_it_is_not_logged_or_echoed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Pacific/Kiritimati is listed in places.json (Kiribati), so a zone that really is not listed stands in for it.
    unlisted = "Antarctica/Troll"
    caplog.set_level(logging.DEBUG)
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type(unlisted)

    assert bot.store.writes == []
    assert "I could not find a time zone for that." in bot.last.text
    assert unlisted not in bot.last.text
    logged = "\n".join(f"{r.getMessage()} {r.exc_text} {r.args}" for r in caplog.records)
    assert unlisted not in logged
    assert "Troll" not in logged


async def test_given_the_canary_zone_is_typed_when_it_is_stored_then_it_never_appears_in_a_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    bot = bot_with(make_policy())
    await _at_zone_question(bot)

    await bot.type(CANARY)

    assert [w[0].zone for w in bot.store.writes] == [CANARY]  # listed, so it is accepted (AC-19)
    logged = "\n".join(f"{r.getMessage()} {r.exc_text} {r.args}" for r in caplog.records)
    assert CANARY not in logged
    assert "Kiritimati" not in logged


async def test_given_zone_paths_when_logs_are_captured_then_no_typed_place_zone_or_nonce_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    bot = bot_with(make_policy(zone=CANARY))
    await _at_zone_question(bot)
    await bot.type("../etc")
    await bot.type("Paris")
    await bot.type("Nwe York")
    await bot.type("Xyzzyville")
    await bot.type("Paris")
    await bot.tap("Paris, France (UTC+1)")

    logged = "\n".join(f"{r.getMessage()} {r.exc_text} {r.args}" for r in caplog.records)
    for secret in (CANARY, "Europe/Paris", "Paris", "Xyzzyville", "Nwe York", "../etc"):
        assert secret not in logged
    nonces = [b.data.rsplit(":", 1)[-1] for m in bot.chat.sent for b in m.buttons]
    assert all(nonce not in logged for nonce in nonces if len(nonce) > 8)


# ---- storing: conflicts and failures (as in U-09) --------------------------------------------------------------------


async def test_given_another_writer_between_question_and_answer_when_answered_then_a_fresh_card_is_shown() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    bot.store.row = StoredSettings(make_policy(remind_at=time(8, 0)), 2, NOW, "web", "someone")

    await bot.type("Tokyo")

    assert bot.store.writes == []
    assert bot.last.text.splitlines()[0].startswith("Your settings changed elsewhere.")
    assert "Remind-me-later default: 08:00" in bot.last.text.splitlines()
    assert bot.labels()[0] == "Change quiet hours"


async def test_given_another_writer_between_choices_and_tap_when_a_button_is_tapped_then_changed_elsewhere() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    await bot.type("Paris")
    bot.store.row = StoredSettings(make_policy(remind_at=time(8, 0)), 2, NOW, "web", "someone")

    await bot.tap("Paris, France (UTC+1)")

    assert bot.store.writes == []
    assert bot.last.text.startswith("Your settings changed elsewhere.")


async def test_given_a_store_failure_when_the_zone_is_saved_then_the_dialogue_ends_with_an_honest_note() -> None:
    bot = bot_with(make_policy())
    await _at_zone_question(bot)
    bot.store.write_error = SettingsStoreFailure("OperationalError", "08006")

    await bot.type("Tokyo")

    assert bot.last.text == "I could not save that. Nothing was changed. Try again in a moment."
    assert await bot.rig.conversations.current() is None
