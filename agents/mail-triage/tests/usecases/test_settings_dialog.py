"""U-quiet-hours-09: the settings dialogue: card, times, quiet hours, conflicts (C-2, C-3, C-8; AC-2, AC-8 to 13)."""
# ruff: noqa: RUF001  # the full-width digits in the refused-forms table are the point of that test row

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

import pytest

from app.db.repos import PolicyRefused, SettingsStoreFailure, StoredSettings, VersionConflict
from app.usecases.settings_dialog import SettingsDialog
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy, validate
from schedule_policy.testing import make_policy
from tests.usecases.test_dispatch import FakeChat, Rig, button, text

if TYPE_CHECKING:
    from app.core.alert_text import AlertMessage, Button
    from app.usecases.dispatch import CommandRouter

USER = 4242
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


class RecordingChat(FakeChat):
    """The fake chat plus ``send`` for messages with several buttons."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[AlertMessage] = []

    async def send(self, message: AlertMessage) -> int:
        self.sent.append(message)
        return len(self.sent)


class FakeSettingsStore:
    """One row with the real store's version rules; failures can be injected."""

    def __init__(self, policy: TimePolicy | None = None) -> None:
        self.row = StoredSettings(policy, 1, NOW, "seed", "seed") if policy else None
        self.writes: list[tuple[TimePolicy, int, str, str]] = []
        self.write_error: Exception | None = None
        self.reads = 0

    async def read(self) -> StoredSettings | None:
        self.reads += 1
        return self.row

    async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
        if self.write_error is not None:
            raise self.write_error
        if problems := validate(policy):
            raise PolicyRefused(problems)
        current = self.row.version if self.row else 0
        if expected_version != current:
            raise VersionConflict
        self.writes.append((policy, expected_version, via, by))
        self.row = StoredSettings(policy, current + 1, NOW, via, by)
        return self.row

    async def undo(self, expected_version: int, via: str, by: str) -> StoredSettings:
        raise AssertionError("undo is not part of this unit")


@dataclass
class Bot:
    """Marco's side of the chat: type text, tap a button by its label, read the last message."""

    store: FakeSettingsStore
    rig: Rig = field(default_factory=Rig)
    chat: RecordingChat = field(init=False)
    router: CommandRouter = field(init=False)

    def __post_init__(self) -> None:
        self.chat = RecordingChat()
        self.rig.chat = self.chat
        self.router = self.rig.router()
        self.dialog = SettingsDialog(self.store, self.chat, self.rig.conversations, USER)
        self.router.register(self.dialog)

    @property
    def last(self) -> AlertMessage:
        return self.chat.sent[-1]

    def labels(self) -> list[str]:
        return [b.label for b in self.last.buttons]

    async def type(self, answer: str) -> None:
        await self.router.handle(text(answer))

    def button_labelled(self, label: str) -> Button:
        matches = [b for b in self.last.buttons if b.label == label]
        assert len(matches) == 1, f"{label!r} not unique in {self.labels()}"
        return matches[0]

    async def tap(self, label: str) -> None:
        await self.router.handle(button(self.button_labelled(label).data))

    async def settings(self) -> None:
        await self.router.handle(text("/settings"))


def bot_with(policy: TimePolicy | None = None) -> Bot:
    return Bot(FakeSettingsStore(policy))


# ---- criterion 1: the card (AC-2) ----------------------------------------------------------------------------------


async def test_given_the_allowed_user_when_settings_is_sent_then_four_labelled_values_each_with_a_change_button() -> (
    None
):
    bot = bot_with(
        make_policy(quiet_start=time(22, 30), quiet_end=time(6, 45), overview_at=time(17, 0), remind_at=time(8, 15))
    )

    await bot.settings()

    lines = bot.last.text.splitlines()
    assert "Quiet hours: 22:30 to 06:45" in lines
    assert "Daily overview: 17:00" in lines
    assert "Remind-me-later default: 08:15" in lines
    assert "Time zone: Europe/Amsterdam" in lines
    assert bot.labels() == [
        "Change quiet hours",
        "Change daily overview",
        "Change remind-me-later default",
        "Change time zone",
    ]


async def test_given_no_stored_row_when_settings_is_sent_then_the_card_shows_the_defaults() -> None:
    bot = bot_with(None)

    await bot.settings()

    lines = bot.last.text.splitlines()
    assert "Quiet hours: 23:00 to 07:00" in lines
    assert "Daily overview: 18:00" in lines
    assert "Remind-me-later default: 09:00" in lines
    assert f"Time zone: {DEFAULT_POLICY.zone}" in lines


async def test_given_the_card_when_shown_then_its_buttons_carry_the_nonce_of_the_stored_conversation() -> None:
    bot = bot_with(None)

    await bot.settings()

    current = await bot.rig.conversations.current()
    assert current is not None
    assert (current.kind, current.step, current.partial) == ("settings", "card", {"version": 0})
    keys = ("quiet", "overview", "remind", "zone")
    assert [b.data for b in bot.last.buttons] == [f"set:{key}:{current.nonce}" for key in keys]


# ---- criterion 2: quiet hours, two steps, one write (AC-13); the single-time questions (AC-8) -----------------------


async def test_given_the_quiet_hours_question_when_a_valid_start_and_end_come_then_both_are_stored_together() -> None:
    bot = bot_with(make_policy())

    await bot.settings()
    await bot.tap("Change quiet hours")
    assert bot.last.text.startswith("Quiet hours, step 1 of 2: start time")
    await bot.type("22:00")
    assert bot.last.text.startswith("Quiet hours, step 2 of 2: end time")
    assert bot.store.writes == []  # nothing is stored after the start alone
    await bot.type("06:00")

    expected = make_policy(quiet_start=time(22, 0), quiet_end=time(6, 0))
    assert bot.store.writes == [(expected, 1, "telegram", str(USER))]
    assert bot.last.text.splitlines()[0] == "Saved."
    assert "Quiet hours: 22:00 to 06:00" in bot.last.text.splitlines()
    assert bot.labels()[0] == "Change quiet hours"  # the card is shown again


async def test_given_no_stored_row_when_quiet_hours_are_saved_then_the_first_row_is_written_at_version_0() -> None:
    bot = bot_with(None)

    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type("22:00")
    await bot.type("06:00")

    assert [(version, via) for _policy, version, via, _by in bot.store.writes] == [(0, "telegram")]
    assert bot.store.writes[0][0] == make_policy(quiet_start=time(22, 0), quiet_end=time(6, 0))


async def test_given_the_overview_question_when_a_time_is_typed_then_only_the_overview_changes() -> None:
    bot = bot_with(make_policy())

    await bot.settings()
    await bot.tap("Change daily overview")
    assert bot.last.text.startswith("Daily overview: type a time, for example 18:00")
    await bot.type("7:30pm")

    assert bot.store.writes == [(make_policy(overview_at=time(19, 30)), 1, "telegram", str(USER))]


async def test_given_the_reminder_question_when_a_time_is_typed_then_only_the_reminder_default_changes() -> None:
    bot = bot_with(make_policy())

    await bot.settings()
    await bot.tap("Change remind-me-later default")
    assert bot.last.text.startswith("Remind-me-later default: type a time, for example 09:00")
    await bot.type("0815")

    assert bot.store.writes == [(make_policy(remind_at=time(8, 15)), 1, "telegram", str(USER))]


# ---- criterion 8: every question names the value and the step and has a Cancel button (a11y) ------------------------


async def test_given_each_question_when_shown_then_it_names_the_value_and_the_step_and_has_cancel() -> None:
    bot = bot_with(make_policy())
    questions: list[tuple[str, str]] = []

    for label, answer in (
        ("Change quiet hours", "22:00"),
        ("Change daily overview", None),
        ("Change remind-me-later default", None),
    ):
        await bot.settings()
        await bot.tap(label)
        questions.append((label, bot.last.text))
        assert bot.labels() == ["Cancel"], label
        if answer:
            await bot.type(answer)
            questions.append((label, bot.last.text))
            assert bot.labels() == ["Cancel"], label

    first_lines = [text.splitlines()[0] for _label, text in questions]
    assert first_lines == [
        "Quiet hours, step 1 of 2: start time",
        "Quiet hours, step 2 of 2: end time",
        "Daily overview: type a time, for example 18:00.",
        "Remind-me-later default: type a time, for example 09:00.",
    ]


# ---- criterion 3: nothing is stored unless both steps finish (AC-13) ------------------------------------------------


async def test_given_a_valid_start_when_marco_cancels_then_nothing_is_stored_and_the_old_values_stay() -> None:
    bot = bot_with(make_policy())
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type("22:00")

    await bot.tap("Cancel")

    assert bot.store.writes == []
    assert bot.rig.chat.edited[-1][1] == "Cancelled. Nothing was changed."
    assert await bot.rig.conversations.current() is None
    assert bot.store.row is not None
    assert bot.store.row.policy == make_policy()


async def test_given_a_valid_start_when_the_end_is_not_a_time_then_nothing_is_stored_and_the_end_is_asked_again() -> (
    None
):
    bot = bot_with(make_policy())
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type("22:00")

    await bot.type("25:00")

    assert bot.store.writes == []
    assert bot.last.text.splitlines()[-2:] == [
        "Quiet hours, step 2 of 2: end time",
        "Start: 22:00. Type a time, for example 07:00.",
    ]
    assert "could not read" in bot.last.text.splitlines()[0]
    assert bot.labels() == ["Cancel"]
    await bot.type("06:00")  # the start is still kept
    assert [w[0] for w in bot.store.writes] == [make_policy(quiet_start=time(22, 0), quiet_end=time(6, 0))]


async def test_given_a_valid_start_when_the_database_fails_at_the_end_then_nothing_is_stored_and_marco_is_told() -> (
    None
):
    bot = bot_with(make_policy())
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type("22:00")
    bot.store.write_error = SettingsStoreFailure("OperationalError", "08006")

    await bot.type("06:00")

    assert bot.store.writes == []
    assert bot.store.row is not None
    assert bot.store.row.policy == make_policy()
    assert bot.last.text == "I could not save that. Nothing was changed. Try again in a moment."
    assert bot.labels() == ["Show settings"]
    assert bot.button_labelled("Show settings").data == "start:settings"


# ---- criterion 4: the refusal names the rule, the value and a working example (C-2, AC-10) -------------------------

_SEEDED = make_policy(overview_at=time(20, 0), remind_at=time(21, 0))


@pytest.mark.parametrize(
    ("start", "end", "sentence"),
    [
        ("22:00", "11:00", "Quiet hours can be 1 to 12 hours. 22:00 to 11:00 is 13 hours. Try 22:00 to 10:00."),
        (
            "07:00",
            "19:01",
            "Quiet hours can be 1 to 12 hours. 07:00 to 19:01 is 12 hours 1 minute. Try 07:00 to 19:00.",
        ),
        ("07:00", "07:30", "Quiet hours can be 1 to 12 hours. 07:00 to 07:30 is 30 minutes. Try 07:00 to 08:00."),
        (
            "23:00",
            "23:00",
            "Quiet hours must start and end at different times. 23:00 to 23:00 is empty. Try 23:00 to 11:00.",
        ),
    ],
)
async def test_given_a_window_outside_one_to_twelve_hours_when_answered_then_it_is_refused_with_rule_value_and_example(
    start: str, end: str, sentence: str
) -> None:
    bot = bot_with(_SEEDED)
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type(start)

    await bot.type(end)

    assert bot.store.writes == []
    assert bot.last.text.splitlines()[0] == sentence
    assert "Quiet hours, step 2 of 2: end time" in bot.last.text  # asked again
    assert bot.labels() == ["Cancel"]


@pytest.mark.parametrize(
    ("start", "end"), [("23:00", "07:00"), ("07:00", "19:00"), ("07:00", "08:00"), ("0:00", "12:00")]
)
async def test_given_windows_of_one_to_twelve_hours_when_answered_then_they_are_stored(start: str, end: str) -> None:
    bot = bot_with(_SEEDED)
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type(start)

    await bot.type(end)

    assert len(bot.store.writes) == 1
    assert bot.last.text.splitlines()[0] == "Saved."


# ---- criterion 6: the typed forms of C-3 inside the dialogue (AC-8, AC-9) -----------------------------------------


@pytest.mark.parametrize(
    ("typed", "shown"),
    [
        ("7", "07:00"),
        ("7:00", "07:00"),
        ("07:00", "07:00"),
        ("0700", "07:00"),
        ("19.30", "19:30"),
        ("7am", "07:00"),
        ("7:30pm", "19:30"),
        ("24:00", "00:00"),
    ],
)
async def test_given_the_accepted_time_forms_when_typed_as_a_start_then_each_is_read_as_the_right_time(
    typed: str, shown: str
) -> None:
    bot = bot_with(_SEEDED)
    await bot.settings()
    await bot.tap("Change quiet hours")

    await bot.type(typed)

    assert f"Start: {shown}." in bot.last.text
    assert bot.store.writes == []


@pytest.mark.parametrize(
    "typed",
    ["abc", "25:00", "07:00:30", "０７:００", "", "1" * 65, "../etc", "'; DROP TABLE x;--", "\x07", "\U0001f600"],
    ids=["word", "hour25", "seconds", "fullwidth", "empty", "too-long", "path", "sql", "control", "emoji"],
)
async def test_given_a_refused_form_when_typed_then_it_is_refused_and_nothing_reaches_the_store(typed: str) -> None:
    bot = bot_with(_SEEDED)
    await bot.settings()
    await bot.tap("Change quiet hours")
    reads = bot.store.reads

    await bot.type(typed)

    assert bot.store.writes == []
    assert bot.store.reads == reads
    assert bot.last.text.splitlines()[-2:] == [
        "Quiet hours, step 1 of 2: start time",
        "Type a time, for example 23:00.",
    ]
    assert "could not read" in bot.last.text.splitlines()[0]
    assert "Try 23:00" in bot.last.text.splitlines()[0]
    assert bot.labels() == ["Cancel"]
    current = await bot.rig.conversations.current()
    assert current is not None
    assert current.step == "quiet_start"
    assert "start" not in current.partial


# ---- criterion 5: quiet hours that would trap the overview or the reminder: one-tap move (AC-11) -------------------


async def _quiet_hours(bot: Bot, start: str, end: str) -> None:
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type(start)
    await bot.type(end)


async def test_given_overview_1800_when_the_window_17_to_03_is_answered_then_it_is_refused_with_a_one_tap_move() -> (
    None
):
    bot = bot_with(make_policy(overview_at=time(18, 0), remind_at=time(9, 0)))

    await _quiet_hours(bot, "17:00", "03:00")

    lines = bot.last.text.splitlines()
    assert (
        lines[0] == "Quiet hours 17:00 to 03:00 are not saved yet: the daily overview at 18:00 would fall inside them."
    )
    assert lines[1] == "Move the daily overview to 03:00 and save both?"
    assert bot.labels() == ["Move to 03:00 and save", "Cancel"]
    assert bot.store.writes == []


async def test_given_the_offered_move_when_taken_then_the_window_and_the_moved_overview_are_stored_in_one_write() -> (
    None
):
    bot = bot_with(make_policy(overview_at=time(18, 0), remind_at=time(9, 0)))
    await _quiet_hours(bot, "17:00", "03:00")

    await bot.tap("Move to 03:00 and save")

    expected = make_policy(quiet_start=time(17, 0), quiet_end=time(3, 0), overview_at=time(3, 0), remind_at=time(9, 0))
    assert bot.store.writes == [(expected, 1, "telegram", str(USER))]
    assert bot.last.text.splitlines()[0] == "Saved."


async def test_given_overview_and_reminder_trapped_when_the_move_is_taken_then_both_move_in_one_write() -> None:
    bot = bot_with(make_policy(overview_at=time(6, 0), remind_at=time(5, 30)))

    await _quiet_hours(bot, "23:00", "07:00")

    lines = bot.last.text.splitlines()
    assert "the daily overview at 06:00 and the remind-me-later default at 05:30 would fall inside them" in lines[0]
    assert lines[1] == "Move the daily overview and the remind-me-later default to 07:00 and save all three?"
    await bot.tap("Move to 07:00 and save")
    assert [w[0] for w in bot.store.writes] == [
        make_policy(quiet_start=time(23, 0), quiet_end=time(7, 0), overview_at=time(7, 0), remind_at=time(7, 0))
    ]


async def test_given_the_offered_move_when_marco_cancels_then_nothing_is_stored() -> None:
    bot = bot_with(make_policy(overview_at=time(18, 0)))
    await _quiet_hours(bot, "17:00", "03:00")

    await bot.tap("Cancel")

    assert bot.store.writes == []
    assert await bot.rig.conversations.current() is None


async def test_given_a_window_that_breaks_the_length_rule_and_traps_the_overview_then_no_move_is_offered() -> None:
    bot = bot_with(make_policy(overview_at=time(23, 30), remind_at=time(9, 0)))

    await _quiet_hours(bot, "22:00", "11:00")

    assert "Quiet hours can be 1 to 12 hours. 22:00 to 11:00 is 13 hours. Try 22:00 to 10:00." in bot.last.text
    assert bot.labels() == ["Cancel"]


async def test_given_text_while_the_move_is_offered_then_the_offer_is_shown_again_with_working_buttons() -> None:
    bot = bot_with(make_policy(overview_at=time(18, 0)))
    await _quiet_hours(bot, "17:00", "03:00")

    await bot.type("yes")
    await bot.tap("Move to 03:00 and save")

    assert len(bot.store.writes) == 1


# ---- criterion 7: a change made elsewhere meanwhile (AC-29) -------------------------------------------------------


async def test_given_the_row_changed_elsewhere_when_the_answer_comes_then_nothing_is_written_and_a_new_card_shows() -> (
    None
):
    bot = bot_with(make_policy())
    await bot.settings()
    await bot.tap("Change daily overview")
    bot.store.row = StoredSettings(make_policy(remind_at=time(8, 0)), 2, NOW, "web", "someone")

    await bot.type("19:00")

    assert bot.store.writes == []
    lines = bot.last.text.splitlines()
    assert lines[0] == "Your settings changed elsewhere. Nothing was saved. These are the current values."
    assert "Remind-me-later default: 08:00" in lines
    assert "Daily overview: 18:00" in lines
    await bot.tap("Change daily overview")  # the fresh card works, at the new version
    await bot.type("19:00")
    assert [(w[1], w[0].overview_at) for w in bot.store.writes] == [(2, time(19, 0))]


async def test_given_the_row_changes_between_the_check_and_the_write_when_saving_then_the_conflict_is_told() -> None:
    class Racing(FakeSettingsStore):
        async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
            raise VersionConflict

    bot = Bot(Racing(make_policy()))
    await bot.settings()
    await bot.tap("Change daily overview")

    await bot.type("19:00")

    assert (
        bot.last.text.splitlines()[0]
        == "Your settings changed elsewhere. Nothing was saved. These are the current values."
    )
    assert bot.labels()[0] == "Change quiet hours"


async def test_given_the_row_changed_elsewhere_when_the_move_is_taken_then_nothing_is_written() -> None:
    bot = bot_with(make_policy(overview_at=time(18, 0)))
    await _quiet_hours(bot, "17:00", "03:00")
    bot.store.row = StoredSettings(make_policy(overview_at=time(18, 0)), 2, NOW, "web", "someone")

    await bot.tap("Move to 03:00 and save")

    assert bot.store.writes == []
    assert bot.last.text.startswith("Your settings changed elsewhere.")


# ---- the time zone question belongs to U-10: until then a marked 'not available yet' branch -----------------------


async def test_given_the_time_zone_button_when_tapped_then_marco_is_told_it_is_not_available_yet() -> None:
    bot = bot_with(make_policy())
    await bot.settings()

    await bot.tap("Change time zone")

    assert bot.last.text.splitlines()[0] == "Changing the time zone is not available yet."
    assert bot.labels()[0] == "Change quiet hours"  # the card, with live buttons
    assert bot.store.writes == []
    await bot.tap("Change daily overview")
    assert bot.last.text.startswith("Daily overview: type a time")


async def test_given_text_on_the_card_when_typed_then_marco_is_pointed_to_the_buttons() -> None:
    bot = bot_with(make_policy())
    await bot.settings()

    await bot.type("hello")

    assert bot.last.text.splitlines()[0] == "Tap one of the Change buttons below."
    assert bot.labels()[0] == "Change quiet hours"


# ---- the single-time questions refuse like the quiet-hours ones; odd buttons never change anything -----------------


@pytest.mark.parametrize("label", ["Change daily overview", "Change remind-me-later default"])
async def test_given_a_single_time_question_when_the_answer_is_not_a_time_then_it_is_asked_again(label: str) -> None:
    bot = bot_with(make_policy())
    await bot.settings()
    await bot.tap(label)
    question = bot.last.text

    await bot.type("later")

    assert bot.last.text.splitlines()[0].startswith('I could not read "later" as a time')
    assert bot.last.text.endswith(question)
    assert bot.labels() == ["Cancel"]
    assert bot.store.writes == []


@pytest.mark.parametrize(
    ("label", "answer", "sentence"),
    [
        ("Change daily overview", "23:30", "The daily overview at 23:30 would fall inside quiet hours. Try 07:00."),
        (
            "Change remind-me-later default",
            "6am",
            "The remind-me-later default at 06:00 would fall inside quiet hours. Try 07:00.",
        ),
    ],
)
async def test_given_an_answer_inside_quiet_hours_when_saved_then_it_is_refused_with_value_and_example(
    label: str, answer: str, sentence: str
) -> None:
    bot = bot_with(make_policy())
    await bot.settings()
    await bot.tap(label)

    await bot.type(answer)

    assert bot.last.text.splitlines()[0] == sentence
    assert bot.store.writes == []


async def test_given_an_undo_button_or_an_unknown_key_when_tapped_on_the_card_then_the_card_is_shown_again() -> None:
    bot = bot_with(make_policy())
    await bot.settings()
    nonce = bot.last.buttons[0].data.rsplit(":", 1)[1]
    await bot.router.handle(button(f"undo:{nonce}"))
    assert bot.last.text.splitlines()[0] == "Quiet hours: 23:00 to 07:00"
    nonce = bot.last.buttons[0].data.rsplit(":", 1)[1]

    await bot.router.handle(button(f"set:bogus:{nonce}"))

    assert bot.last.text.splitlines()[0] == "Quiet hours: 23:00 to 07:00"
    assert bot.store.writes == []


async def test_given_a_store_that_refuses_the_policy_at_write_time_when_saving_then_the_refusal_is_worded() -> None:
    class Skewed(FakeSettingsStore):
        async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
            raise PolicyRefused(validate(make_policy(quiet_end=time(23, 0))))

    bot = Bot(Skewed(make_policy()))
    await bot.settings()
    await bot.tap("Change daily overview")

    await bot.type("19:00")

    assert bot.last.text.splitlines()[0].startswith("Quiet hours must start and end at different times.")
    assert bot.labels() == ["Cancel"]


@pytest.mark.parametrize("entry", ["begin", "ask", "save"])
async def test_given_a_conversation_that_expired_meanwhile_when_the_dialogue_moves_on_then_nothing_is_sent(
    entry: str,
) -> None:
    bot = bot_with(make_policy())
    await bot.settings()
    await bot.tap("Change daily overview")
    current = await bot.rig.conversations.current()
    assert current is not None
    sent = len(bot.chat.sent)
    await bot.rig.conversations.clear()  # the question expired or was replaced after the router claimed it

    if entry == "begin":
        await bot.dialog.begin(current)
    elif entry == "ask":
        await bot.dialog.on_button(replace(current, step="card"), "set", "quiet")
    else:
        await bot.dialog.on_text(current, "19:00")

    assert len(bot.chat.sent) == sent
    assert len(bot.store.writes) == (
        1 if entry == "save" else 0
    )  # the write itself is version-checked, not nonce-checked


# ---- criterion 9: nothing leaks into the logs (AC-33) --------------------------------------------------------------

CANARY = "Pacific/Kiritimati"
TOKEN = "123456:ABC-secret-token"  # noqa: S105  # a fake bot token typed by mistake


async def test_given_failure_paths_when_logs_are_captured_then_no_zone_token_answer_or_nonce_appears(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    bot = bot_with(make_policy(zone=CANARY, overview_at=time(18, 0)))
    await bot.settings()
    await bot.tap("Change quiet hours")
    await bot.type(TOKEN)  # refused
    await bot.type("../etc")  # refused
    await bot.type("17:00")
    await bot.type("03:00")  # the move is offered
    bot.store.row = StoredSettings(make_policy(zone=CANARY), 2, NOW, "web", "someone")
    await bot.tap("Move to 03:00 and save")  # changed elsewhere
    await bot.tap("Change daily overview")
    bot.store.write_error = SettingsStoreFailure("OperationalError", "08006")
    await bot.type("19:00")  # the database fails

    assert [m.text for m in bot.chat.sent][-1].startswith("I could not save that.")
    assert any(CANARY in m.text for m in bot.chat.sent)  # the card does show the zone to Marco ...
    logged = "\n".join(f"{record.getMessage()} {record.exc_text} {record.args}" for record in caplog.records)
    for secret in (CANARY, TOKEN, "../etc", "123456"):  # ... but never to a log
        assert secret not in logged
    assert "08006" in logged  # the class and SQLSTATE are logged
    nonces = [piece for message in bot.chat.sent for b in message.buttons for piece in b.data.split(":")[-1:]]
    assert all(nonce not in logged for nonce in nonces if len(nonce) > 8)
