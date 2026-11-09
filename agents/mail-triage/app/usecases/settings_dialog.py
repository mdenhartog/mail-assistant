"""The settings dialogue (spec C-2, C-3, C-8; Behaviour 1 to 5; ADR-0025, ADR-0026).

``SettingsDialog`` is a ``DialogueHandler`` of kind ``settings``. The router starts the conversation, claims every
button and answer (rotating the nonce) and handles Cancel; this class decides what to ask and what to store.

Every write is the WHOLE new policy through ``SettingsStore.write`` with the version the card was shown at, so a change
made elsewhere meanwhile is a ``VersionConflict`` and never overwritten. Nothing here logs a typed answer, a nonce, a
token or a zone: failures are logged by class and SQLSTATE only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

from app.core import settings_text
from app.usecases.dispatch import SETTINGS_TTL, button_data
from schedule_policy.policy import DEFAULT_POLICY

if TYPE_CHECKING:
    from datetime import timedelta

    from app.core.alert_text import AlertMessage
    from app.db.pg_conversation import Kind, OpenConversation
    from app.db.repos import SettingsStore
    from app.usecases.dispatch import ConversationPort
    from schedule_policy.policy import TimePolicy

CARD = "card"


class DialogChat(Protocol):
    """What the dialogue needs from Telegram: a message with buttons."""

    async def send(self, message: AlertMessage) -> int:
        """Send a message with its buttons; return the Telegram message id."""
        ...


class SettingsDialog:
    """Shows the settings card and asks the questions behind its Change buttons."""

    kind: ClassVar[Kind] = "settings"
    commands: ClassVar[frozenset[str]] = frozenset({"/settings"})
    first_step: ClassVar[str] = CARD
    ttl: ClassVar[timedelta | None] = SETTINGS_TTL

    def __init__(
        self, store: SettingsStore, chat: DialogChat, conversations: ConversationPort, allowed_user_id: int
    ) -> None:
        """Wire the settings store, Telegram, the stored conversation and the one user who may change settings."""
        self._store = store
        self._chat = chat
        self._conversations = conversations
        self._by = str(allowed_user_id)

    async def begin(self, conversation: OpenConversation) -> None:
        """Show the card."""
        stored = await self._store.read()
        policy = stored.policy if stored else DEFAULT_POLICY
        version = stored.version if stored else 0
        moved = await self._conversations.advance(conversation.nonce, CARD, {"version": version})
        if moved is not None:
            await self._show_card(moved.nonce, policy)

    async def on_text(self, conversation: OpenConversation, text: str) -> None:
        """Marco typed an answer."""
        raise NotImplementedError

    async def on_button(self, conversation: OpenConversation, action: str, argument: str) -> None:
        """Marco tapped a button."""
        raise NotImplementedError

    async def _show_card(self, nonce: str, policy: TimePolicy, note: str | None = None) -> None:
        change = {key: button_data("set", nonce, key) for key in settings_text.VALUE_NAMES}
        await self._chat.send(settings_text.card(policy, change, note))
