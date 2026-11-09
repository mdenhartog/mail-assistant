"""The settings dialogue (spec C-2, C-3, C-8; Behaviour 1 to 5; ADR-0025, ADR-0026).

``SettingsDialog`` is a ``DialogueHandler`` of kind ``settings``. The router starts the conversation, claims every
button and answer (rotating the nonce) and handles Cancel; this class decides what to ask and what to store.

Every write is the WHOLE new policy through ``SettingsStore.write`` with the version the card was shown at, so a change
made elsewhere meanwhile is a ``VersionConflict`` and never overwritten. Nothing here logs a typed answer, a nonce, a
token or a zone: failures are logged by class and SQLSTATE only.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import time
from typing import TYPE_CHECKING, ClassVar, Protocol

from app.core import settings_text
from app.usecases.dispatch import SETTINGS_TTL, button_data
from schedule_policy.parse import parse_time
from schedule_policy.policy import DEFAULT_POLICY

if TYPE_CHECKING:
    from datetime import timedelta

    from app.core.alert_text import AlertMessage
    from app.db.pg_conversation import Kind, OpenConversation
    from app.db.repos import SettingsStore
    from app.usecases.dispatch import ConversationPort
    from schedule_policy.policy import TimePolicy

CARD = "card"
QUIET_START = "quiet_start"
QUIET_END = "quiet_end"
OVERVIEW = settings_text.OVERVIEW
REMIND = settings_text.REMIND
SAVED = "Saved."
_SINGLE_TIME_FIELD = {OVERVIEW: "overview_at", REMIND: "remind_at"}


class DialogChat(Protocol):
    """What the dialogue needs from Telegram: a message with buttons."""

    async def send(self, message: AlertMessage) -> int:
        """Send a message with its buttons; return the Telegram message id."""
        ...


def _hhmm(value: object) -> time:
    """A clock time kept in a conversation's ``partial`` as ``HH:MM`` text."""
    hour, minute = str(value).split(":")
    return time(int(hour), int(minute))


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
        step = conversation.step
        if step in _SINGLE_TIME_FIELD:
            await self._single_time(conversation, text)
        elif step == QUIET_START:
            await self._quiet_start(conversation, text)
        elif step == QUIET_END:
            await self._quiet_end(conversation, text)
        else:
            await self._repeat(conversation)

    async def on_button(self, conversation: OpenConversation, action: str, argument: str) -> None:
        """Marco tapped a button."""
        if action == "set" and conversation.step == CARD:
            await self._ask(conversation, argument)
        else:
            await self._repeat(conversation)

    # ---- questions -----------------------------------------------------------------------------------------------

    async def _ask(self, conversation: OpenConversation, key: str) -> None:
        if key == settings_text.QUIET:
            await self._question(conversation, QUIET_START, conversation.partial, settings_text.quiet_start_question())
        elif key in _SINGLE_TIME_FIELD:
            await self._question(conversation, key, conversation.partial, settings_text.time_question(key))
        else:
            await self._repeat(conversation)

    async def _question(
        self, conversation: OpenConversation, step: str, partial: dict[str, object], question: str
    ) -> None:
        """Move to ``step`` (new nonce) and ask ``question`` with a Cancel button bound to that nonce."""
        moved = await self._conversations.advance(conversation.nonce, step, partial)
        if moved is not None:
            await self._chat.send(settings_text.with_cancel(question, button_data("cancel", moved.nonce)))

    async def _repeat(self, conversation: OpenConversation) -> None:
        """Ask the current step again, with the nonce the router just issued."""
        raise NotImplementedError

    # ---- answers -------------------------------------------------------------------------------------------------

    async def _single_time(self, conversation: OpenConversation, text: str) -> None:
        answer = parse_time(text)
        if answer is None:
            await self._repeat(conversation)
            return
        await self._save(conversation, {_SINGLE_TIME_FIELD[conversation.step]: answer})

    async def _quiet_start(self, conversation: OpenConversation, text: str) -> None:
        start = parse_time(text)
        if start is None:
            await self._repeat(conversation)
            return
        partial = {**conversation.partial, "start": settings_text.clock(start)}
        await self._question(conversation, QUIET_END, partial, settings_text.quiet_end_question(start))

    async def _quiet_end(self, conversation: OpenConversation, text: str) -> None:
        end = parse_time(text)
        if end is None:
            await self._repeat(conversation)
            return
        start = _hhmm(conversation.partial["start"])
        await self._save(conversation, {"quiet_start": start, "quiet_end": end})

    # ---- storing -------------------------------------------------------------------------------------------------

    async def _save(self, conversation: OpenConversation, changes: dict[str, time]) -> None:
        """Store the whole new policy at the version the card was shown at, then show the card again."""
        stored = await self._store.read()
        proposed: TimePolicy = replace(stored.policy if stored else DEFAULT_POLICY, **changes)
        written = await self._store.write(proposed, int(str(conversation.partial["version"])), "telegram", self._by)
        moved = await self._conversations.advance(conversation.nonce, CARD, {"version": written.version})
        if moved is not None:
            await self._show_card(moved.nonce, written.policy, SAVED)

    async def _show_card(self, nonce: str, policy: TimePolicy, note: str | None = None) -> None:
        change = {key: button_data("set", nonce, key) for key in settings_text.VALUE_NAMES}
        await self._chat.send(settings_text.card(policy, change, note))
