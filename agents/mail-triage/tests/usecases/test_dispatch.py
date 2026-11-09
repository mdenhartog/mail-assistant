"""Routing of Marco's button presses and typed answers to the use cases (spec AC-6 to AC-10, AC-15)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import pytest

from app.adapters.telegram_inbox import Command
from app.core.alert_state import AlertState
from app.usecases.dispatch import CommandRouter
from app.usecases.reply import StoredDraft
from schedule_policy.testing import FakeClock
from tests.usecases.fakes_dialogue import FakeConversations, FakeSettings


_UPDATE_IDS = itertools.count(1)


def button(data: str, update_id: int | None = None) -> Command:
    return Command("button", data, 1, 9, "cb1", next(_UPDATE_IDS) if update_id is None else update_id)


def text(data: str, update_id: int | None = None) -> Command:
    return Command("text", data, 1, 10, None, next(_UPDATE_IDS) if update_id is None else update_id)


@dataclass
class FakeReply:
    calls: list[tuple[str, ...]] = field(default_factory=list)

    async def begin(self, alert_id: str) -> None:
        self.calls.append(("begin", alert_id))

    async def start_reply(self, alert_id: str, text: str) -> None:
        self.calls.append(("start_reply", alert_id, text))

    async def confirm(self, draft_id: str, token: str) -> None:
        self.calls.append(("confirm", draft_id, token))

    async def edit(self, draft_id: str) -> None:
        self.calls.append(("edit", draft_id))

    async def cancel(self, draft_id: str) -> None:
        self.calls.append(("cancel", draft_id))


@dataclass
class FakeSnooze:
    calls: list[tuple[str, ...]] = field(default_factory=list)
    store: FakeStore | None = None

    async def snooze(self, alert_id: str, answer: str) -> None:
        self.calls.append(("snooze", alert_id, answer))
        if self.store and answer == "3":
            self.store.states[alert_id] = AlertState.SNOOZED

    async def close(self, alert_id: str) -> None:
        self.calls.append(("close", alert_id))


@dataclass
class FakeStore:
    waiting: tuple[str, str] | None = None
    states: dict[str, AlertState] = field(default_factory=dict)
    drafts: dict[str, StoredDraft] = field(default_factory=dict)

    async def set_awaiting(self, alert_id: str, kind: str | None) -> None:
        self.waiting = (alert_id, kind) if kind else None

    async def awaiting(self) -> tuple[str, str] | None:
        return self.waiting

    async def state_of(self, alert_id: str) -> AlertState | None:
        return self.states.get(alert_id)

    async def get_draft(self, draft_id: str) -> StoredDraft | None:
        return self.drafts.get(draft_id)


class FakeChat:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.acknowledged: list[str] = []
        self.edited: list[tuple[int, str]] = []
        self.offered: list[tuple[str, str, str]] = []

    async def say(self, text: str) -> None:
        self.said.append(text)

    async def answer_callback(self, callback_id: str) -> None:
        self.acknowledged.append(callback_id)

    async def edit_message(self, message_id: int, text: str) -> None:
        self.edited.append((message_id, text))

    async def offer(self, text: str, label: str, data: str) -> None:
        self.offered.append((text, label, data))


@dataclass
class Rig:
    reply: FakeReply = field(default_factory=FakeReply)
    snooze: FakeSnooze = field(default_factory=FakeSnooze)
    store: FakeStore = field(default_factory=FakeStore)
    chat: FakeChat = field(default_factory=FakeChat)
    clock: FakeClock = field(default_factory=FakeClock)
    conversations: FakeConversations = field(init=False)
    settings: FakeSettings = field(default_factory=FakeSettings)

    def __post_init__(self) -> None:
        self.conversations = FakeConversations(self.clock)

    def router(self) -> CommandRouter:
        self.snooze.store = self.store
        return CommandRouter(self.reply, self.snooze, self.store, self.chat, self.conversations)


async def test_given_the_reply_button_when_pressed_then_the_reply_starts_and_the_next_text_is_the_reply() -> None:
    rig = Rig()

    await rig.router().handle(button("reply:5"))
    await rig.router().handle(text("Yes, tomorrow."))

    assert rig.reply.calls == [("begin", "5"), ("start_reply", "5", "Yes, tomorrow.")]
    assert rig.chat.acknowledged == ["cb1"]


async def test_given_remind_me_later_when_pressed_then_marco_is_asked_and_valid_hours_snooze_it() -> None:
    rig = Rig()

    await rig.router().handle(button("later:5"))
    assert "hours" in rig.chat.said[-1]
    await rig.router().handle(text("3"))

    assert rig.snooze.calls == [("snooze", "5", "3")]
    assert rig.store.waiting is None  # the question is answered


async def test_given_invalid_hours_when_typed_then_the_question_stays_open() -> None:
    rig = Rig()
    await rig.router().handle(button("later:5"))

    await rig.router().handle(text("soon"))

    assert rig.snooze.calls == [("snooze", "5", "soon")]
    assert rig.store.waiting == ("5", "snooze_hours")


async def test_given_no_more_reminders_when_pressed_then_the_alert_is_closed_and_nothing_is_awaited() -> None:
    rig = Rig()
    await rig.router().handle(button("later:5"))

    await rig.router().handle(button("stop:5"))

    assert rig.snooze.calls == [("close", "5")]
    assert rig.store.waiting is None


async def test_given_the_draft_buttons_when_pressed_then_they_reach_the_reply_flow() -> None:
    rig = Rig()
    rig.store.drafts["d1"] = StoredDraft("d1", "5", None, "Yes", "a" * 64, expires_at=None, used=False)  # type: ignore[arg-type]
    await rig.router().handle(button("reply:5"))

    await rig.router().handle(button("edit:d1"))
    await rig.router().handle(button("send:d1:abcdef0123456789"))
    await rig.router().handle(button("cancel:d1"))

    assert rig.reply.calls[1:] == [("edit", "d1"), ("confirm", "d1", "abcdef0123456789"), ("cancel", "d1")]
    assert rig.store.waiting is None  # sending or cancelling ends the typing


async def test_given_text_when_nothing_is_awaited_then_marco_is_pointed_to_the_buttons() -> None:
    rig = Rig()

    await rig.router().handle(text("hello?"))

    assert rig.reply.calls == []
    assert rig.snooze.calls == []
    assert "buttons" in rig.chat.said[-1]


@pytest.mark.parametrize(
    "data", ["", "unknown:1", "reply", "reply:", "send:d1", "reply:5:extra", "x" * 64, "reply:../etc"]
)
async def test_given_malformed_or_unknown_button_data_when_pressed_then_nothing_runs(data: str) -> None:
    rig = Rig()

    await rig.router().handle(button(data))

    assert rig.reply.calls == []
    assert rig.snooze.calls == []
    assert rig.chat.acknowledged == ["cb1"]  # the spinner still stops
