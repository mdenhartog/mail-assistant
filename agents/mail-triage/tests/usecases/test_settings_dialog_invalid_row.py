"""U-quiet-hours-16c: /settings repairs an invalid stored row instead of going silent (RT-1; ADR-0025, ADR-0026)."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from app.db.repos import SettingsView, StoredSettings, StoredSettingsInvalid, VersionConflict
from schedule_policy.testing import make_policy
from tests.usecases.test_settings_dialog import NOW, USER, Bot, FakeSettingsStore

if TYPE_CHECKING:
    from schedule_policy.policy import TimePolicy

INVALID_VERSION = 3
NOTE = "The saved settings are not valid"


class InvalidRowStore(FakeSettingsStore):
    """A store whose one row is invalid at ``INVALID_VERSION``: strict ``read`` raises, the dialogue read says so."""

    def __init__(self) -> None:
        super().__init__(None)
        self.invalid = True

    async def read(self) -> StoredSettings | None:
        if self.invalid:
            raise StoredSettingsInvalid(("zone_unknown",))
        return await super().read()

    async def read_for_dialogue(self) -> SettingsView:
        if self.invalid:
            return SettingsView(INVALID_VERSION, None, ("zone_unknown",))
        return await super().read_for_dialogue()

    async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
        if not self.invalid:
            return await super().write(policy, expected_version, via, by)
        if expected_version != INVALID_VERSION:
            raise VersionConflict
        self.invalid = False
        self.writes.append((policy, expected_version, via, by))
        self.row = StoredSettings(policy, INVALID_VERSION + 1, NOW, via, by)
        return self.row


def _bot(in_use: TimePolicy | None = None) -> Bot:
    return Bot(InvalidRowStore(), in_use=in_use) if in_use else Bot(InvalidRowStore())


async def test_given_an_invalid_stored_row_when_settings_is_sent_then_the_card_shows_the_values_in_use_and_a_note() -> (
    None
):
    in_use = make_policy(quiet_start=time(22, 30), quiet_end=time(6, 45), overview_at=time(17, 0))
    bot = _bot(in_use)

    await bot.settings()

    lines = bot.last.text.splitlines()
    assert lines[0].startswith(NOTE)
    assert "Quiet hours: 22:30 to 06:45" in lines
    assert "Daily overview: 17:00" in lines
    assert bot.labels()[0] == "Change quiet hours"
    current = await bot.rig.conversations.current()
    assert current is not None
    assert (current.step, current.partial) == ("card", {"version": INVALID_VERSION})


async def test_given_an_invalid_row_and_no_last_good_values_when_settings_is_sent_then_the_defaults_are_shown() -> None:
    bot = _bot()

    await bot.settings()

    assert "Quiet hours: 23:00 to 07:00" in bot.last.text.splitlines()
    assert bot.last.text.startswith(NOTE)


async def test_given_the_invalid_card_when_a_valid_answer_is_given_then_a_whole_new_row_is_written_at_its_version() -> (
    None
):
    in_use = make_policy(quiet_start=time(22, 30), quiet_end=time(6, 45))
    bot = _bot(in_use)
    await bot.settings()
    await bot.tap("Change daily overview")

    await bot.type("19:00")

    whole = make_policy(quiet_start=time(22, 30), quiet_end=time(6, 45), overview_at=time(19, 0))
    assert bot.store.writes == [(whole, INVALID_VERSION, "telegram", str(USER))]
    assert bot.last.text.splitlines()[0] == "Saved."


async def test_given_the_invalid_card_when_text_is_typed_then_the_card_comes_back_with_the_note() -> None:
    bot = _bot()
    await bot.settings()

    await bot.type("hello")

    assert bot.last.text.startswith(NOTE)
    assert bot.labels()[0] == "Change quiet hours"


async def test_given_the_row_was_repaired_elsewhere_when_an_answer_comes_then_the_changed_elsewhere_card_has_no_note() -> (
    None
):
    bot = _bot()
    await bot.settings()
    await bot.tap("Change daily overview")
    store = bot.store
    assert isinstance(store, InvalidRowStore)
    store.invalid = False
    store.row = StoredSettings(make_policy(), INVALID_VERSION + 1, NOW, "web", "someone")

    await bot.type("19:00")

    assert store.writes == []
    assert bot.last.text.startswith("Your settings changed elsewhere.")
    assert NOTE not in bot.last.text
