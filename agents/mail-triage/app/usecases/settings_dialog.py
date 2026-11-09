"""The settings dialogue (spec C-2, C-3, C-8; Behaviour 1 to 5; ADR-0025, ADR-0026).

``SettingsDialog`` is a ``DialogueHandler`` of kind ``settings``. The router starts the conversation, claims every
button and answer (rotating the nonce) and handles Cancel; this class decides what to ask and what to store.

Every write is the WHOLE new policy through ``SettingsStore.write`` with the version the card was shown at, so a change
made elsewhere meanwhile is a ``VersionConflict`` and never overwritten. Nothing here logs a typed answer, a nonce, a
token or a zone: failures are logged by class and SQLSTATE only.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import time
from typing import TYPE_CHECKING, ClassVar, Protocol

from app.core import settings_text
from app.db.repos import PolicyRefused, SettingsStoreFailure
from app.usecases.dispatch import SETTINGS_TTL, button_data
from schedule_policy.parse import parse_time
from schedule_policy.policy import DEFAULT_POLICY, validate

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import timedelta

    from app.core.alert_text import AlertMessage
    from app.db.pg_conversation import Kind, OpenConversation
    from app.db.repos import SettingsStore
    from app.usecases.dispatch import ConversationPort
    from schedule_policy.policy import Problem, TimePolicy

logger = logging.getLogger(__name__)

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


_EXAMPLE = {QUIET_START: "23:00", QUIET_END: "07:00", OVERVIEW: "18:00", REMIND: "09:00"}


def _question_text(conversation: OpenConversation) -> str:
    """The question of the conversation's current step."""
    if conversation.step == QUIET_START:
        return settings_text.quiet_start_question()
    if conversation.step == QUIET_END:
        return settings_text.quiet_end_question(_hhmm(conversation.partial["start"]))
    return settings_text.time_question(conversation.step)


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
        async with self._guard():
            stored = await self._store.read()
            policy = stored.policy if stored else DEFAULT_POLICY
            version = stored.version if stored else 0
            moved = await self._conversations.advance(conversation.nonce, CARD, {"version": version})
            if moved is not None:
                await self._show_card(moved.nonce, policy)

    async def on_text(self, conversation: OpenConversation, text: str) -> None:
        """Marco typed an answer."""
        async with self._guard():
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
        async with self._guard():
            if action == "set" and conversation.step == CARD:
                await self._ask(conversation, argument)
            else:
                await self._repeat(conversation)

    @asynccontextmanager
    async def _guard(self) -> AsyncIterator[None]:
        """A store failure ends the dialogue with an honest note; nothing was written by the failed call."""
        try:
            yield
        except SettingsStoreFailure as failure:
            logger.warning("settings store failed cause=%s sqlstate=%s", failure.cause_class, failure.sqlstate)
            await self._conversations.clear()
            await self._chat.send(settings_text.with_start_button(settings_text.SAVE_FAILED))

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

    async def _repeat(self, conversation: OpenConversation, lead: str | None = None) -> None:
        """Ask the current step again, with the nonce the router just issued; ``lead`` explains why."""
        step = conversation.step
        if step not in _EXAMPLE:  # the card, or a step this dialogue does not know: show the card
            stored = await self._store.read()
            await self._show_card(conversation.nonce, stored.policy if stored else DEFAULT_POLICY, lead)
            return
        question = _question_text(conversation)
        text = f"{lead}\n\n{question}" if lead else question
        await self._chat.send(settings_text.with_cancel(text, button_data("cancel", conversation.nonce)))

    # ---- answers -------------------------------------------------------------------------------------------------

    async def _single_time(self, conversation: OpenConversation, text: str) -> None:
        answer = parse_time(text)
        if answer is None:
            await self._repeat(conversation, settings_text.unreadable(text, _EXAMPLE[conversation.step]))
            return
        await self._save(conversation, {_SINGLE_TIME_FIELD[conversation.step]: answer})

    async def _quiet_start(self, conversation: OpenConversation, text: str) -> None:
        start = parse_time(text)
        if start is None:
            await self._repeat(conversation, settings_text.unreadable(text, _EXAMPLE[QUIET_START]))
            return
        partial = {**conversation.partial, "start": settings_text.clock(start)}
        await self._question(conversation, QUIET_END, partial, settings_text.quiet_end_question(start))

    async def _quiet_end(self, conversation: OpenConversation, text: str) -> None:
        end = parse_time(text)
        if end is None:
            await self._repeat(conversation, settings_text.unreadable(text, _EXAMPLE[QUIET_END]))
            return
        start = _hhmm(conversation.partial["start"])
        await self._save(conversation, {"quiet_start": start, "quiet_end": end})

    # ---- storing -------------------------------------------------------------------------------------------------

    async def _save(self, conversation: OpenConversation, changes: dict[str, time]) -> None:
        """Store the whole new policy at the version the card was shown at, then show the card again."""
        stored = await self._store.read()
        proposed: TimePolicy = replace(stored.policy if stored else DEFAULT_POLICY, **changes)
        if problems := validate(proposed):
            await self._refuse(conversation, proposed, problems)
            return
        try:
            written = await self._store.write(proposed, int(str(conversation.partial["version"])), "telegram", self._by)
        except PolicyRefused as refused:  # another writer's change made it invalid between the read and the write
            await self._refuse(conversation, proposed, refused.problems)
            return
        moved = await self._conversations.advance(conversation.nonce, CARD, {"version": written.version})
        if moved is not None:
            await self._show_card(moved.nonce, written.policy, SAVED)

    async def _refuse(self, conversation: OpenConversation, proposed: TimePolicy, problems: list[Problem]) -> None:
        """Say which rules the answer breaks and ask the same question again; nothing is stored."""
        lead = " ".join(settings_text.refusal(problem, proposed.window_minutes) for problem in problems)
        await self._repeat(conversation, lead)

    async def _show_card(self, nonce: str, policy: TimePolicy, note: str | None = None) -> None:
        change = {key: button_data("set", nonce, key) for key in settings_text.VALUE_NAMES}
        await self._chat.send(settings_text.card(policy, change, note))
