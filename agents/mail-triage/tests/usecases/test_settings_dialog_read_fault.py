"""U-quiet-hours-05b: a read fault during /settings ends the dialogue cleanly (AC-33)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repos import SettingsStoreFailure
from app.usecases.settings_dialog import SettingsDialog
from schedule_policy.policy import DEFAULT_POLICY
from tests.usecases.test_dispatch import FakeChat, Rig, text

if TYPE_CHECKING:
    from app.core.alert_text import AlertMessage
    from app.db.repos import SettingsView

USER = 4242


class SentChat(FakeChat):
    """The fake chat plus ``send`` for messages with buttons."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[AlertMessage] = []

    async def send(self, message: AlertMessage) -> int:
        self.sent.append(message)
        return len(self.sent)


class UnreadableStore:
    """A settings store whose database cannot answer a read."""

    async def read_for_dialogue(self) -> SettingsView:
        raise SettingsStoreFailure("UndefinedTableError", "42P01")


async def test_given_a_read_fault_when_settings_is_sent_then_the_dialogue_ends_with_the_store_failure_message() -> None:
    rig = Rig()
    chat = SentChat()
    rig.chat = chat
    router = rig.router()
    router.register(
        SettingsDialog(UnreadableStore(), chat, rig.conversations, USER, rig.clock.now, lambda: DEFAULT_POLICY)
    )  # type: ignore[arg-type]

    await router.handle(text("/settings"))

    assert [m.text for m in chat.sent] == ["I could not save that. Nothing was changed. Try again in a moment."]
    assert [b.label for b in chat.sent[-1].buttons] == ["Show settings"]


class RefusedStore:
    """A settings store whose connection is refused: the raw error can reach ``read`` unwrapped."""

    async def read_for_dialogue(self) -> SettingsView:
        raise ConnectionRefusedError("[Errno 111] Connect call failed ('10.0.0.5', 5432)")


async def test_given_a_refused_connection_when_settings_is_sent_then_the_dialogue_ends_like_a_store_failure() -> None:
    rig = Rig()
    chat = SentChat()
    rig.chat = chat
    router = rig.router()
    router.register(
        SettingsDialog(RefusedStore(), chat, rig.conversations, USER, rig.clock.now, lambda: DEFAULT_POLICY)
    )  # type: ignore[arg-type]

    await router.handle(text("/settings"))

    assert [m.text for m in chat.sent] == ["I could not save that. Nothing was changed. Try again in a moment."]
    assert [b.label for b in chat.sent[-1].buttons] == ["Show settings"]
    assert await rig.conversations.current() is None
