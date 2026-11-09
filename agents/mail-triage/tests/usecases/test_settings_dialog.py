"""U-quiet-hours-09: the settings dialogue: card, times, quiet hours, conflicts (spec C-2, C-3, C-8; AC-2, AC-8 to AC-13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time

from app.core.alert_text import AlertMessage, Button
from app.db.repos import PolicyRefused, StoredSettings, VersionConflict
from app.usecases.dispatch import CommandRouter
from app.usecases.settings_dialog import SettingsDialog
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy, validate
from schedule_policy.testing import make_policy
from tests.usecases.test_dispatch import FakeChat, Rig, button, text

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
        self.router.register(SettingsDialog(self.store, self.chat, self.rig.conversations, USER))

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
