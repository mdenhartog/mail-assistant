"""The settings dialogue (spec C-2, C-3, C-8; Behaviour 1 to 5; ADR-0025, ADR-0026).

``SettingsDialog`` is a ``DialogueHandler`` of kind ``settings``. The router starts the conversation, claims every
button and answer (rotating the nonce) and handles Cancel; this class decides what to ask and what to store.

Every write is the WHOLE new policy through ``SettingsStore.write`` with the version the card was shown at, so a change
made elsewhere meanwhile is a ``VersionConflict`` and never overwritten. Nothing here logs a typed answer, a nonce, a
token or a zone: failures are logged by class and SQLSTATE only.

Not in this unit: the time zone question (U-quiet-hours-10; its button answers "not available yet" until then) and the
full-picture confirmation with Undo (U-quiet-hours-11; after a save the card is shown again under a plain "Saved.").
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import time
from typing import TYPE_CHECKING, ClassVar, Protocol

from app.core import settings_text
from app.db.repos import PolicyRefused, SettingsStoreFailure, VersionConflict
from app.usecases.dispatch import SETTINGS_TTL, button_data
from schedule_policy.parse import parse_time
from schedule_policy.policy import DEFAULT_POLICY, validate

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from datetime import timedelta

    from app.core.alert_text import AlertMessage
    from app.db.pg_conversation import Kind, OpenConversation
    from app.db.repos import SettingsStore, StoredSettings
    from app.usecases.dispatch import ConversationPort
    from schedule_policy.policy import Problem, TimePolicy

logger = logging.getLogger(__name__)

CARD = "card"
ASK_START = "quiet_start"
ASK_END = "quiet_end"
CONFLICT = "conflict"
OVERVIEW = settings_text.OVERVIEW
REMIND = settings_text.REMIND
MOVE = "move"
SAVED = "Saved."
_SINGLE_TIME_FIELD = {OVERVIEW: "overview_at", REMIND: "remind_at"}
_MOVED_FIELD = {"overview_in_quiet_hours": "overview_at", "remind_in_quiet_hours": "remind_at"}
_EXAMPLE = {ASK_START: "23:00", ASK_END: "07:00", OVERVIEW: "18:00", REMIND: "09:00"}


class DialogChat(Protocol):
    """What the dialogue needs from Telegram: a message with buttons."""

    async def send(self, message: AlertMessage) -> int:
        """Send a message with its buttons; return the Telegram message id."""
        ...


def _hhmm(value: object) -> time:
    """A clock time kept in a conversation's ``partial`` as ``HH:MM`` text."""
    hour, minute = str(value).split(":")
    return time(int(hour), int(minute))


def _question_text(conversation: OpenConversation) -> str:
    """The question of the conversation's current step."""
    if conversation.step == ASK_START:
        return settings_text.quiet_start_question()
    if conversation.step == ASK_END:
        return settings_text.quiet_end_question(_hhmm(conversation.partial["start"]))
    return settings_text.time_question(conversation.step)


def _version(stored: StoredSettings | None) -> int:
    return stored.version if stored else 0


def _policy(stored: StoredSettings | None) -> TimePolicy:
    return stored.policy if stored else DEFAULT_POLICY


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
            await self._card(conversation, None)

    async def on_text(self, conversation: OpenConversation, text: str) -> None:
        """Marco typed an answer."""
        async with self._guard():
            step = conversation.step
            if step in _SINGLE_TIME_FIELD:
                await self._single_time(conversation, text)
            elif step == ASK_START:
                await self._quiet_start(conversation, text)
            elif step == ASK_END:
                await self._quiet_end(conversation, text)
            else:
                await self._repeat(conversation, settings_text.TAP_A_BUTTON if step == CARD else None)

    async def on_button(self, conversation: OpenConversation, action: str, argument: str) -> None:
        """Marco tapped a button."""
        async with self._guard():
            if action == "set" and conversation.step == CARD:
                await self._ask(conversation, argument)
            elif action == "set" and conversation.step == CONFLICT and argument == MOVE:
                await self._move(conversation)
            else:
                await self._repeat(conversation)

    @asynccontextmanager
    async def _guard(self) -> AsyncGenerator[None]:
        """A store failure ends the dialogue with an honest note; nothing was written by the failed call."""
        try:
            yield
        except SettingsStoreFailure as failure:
            logger.warning("settings store failed cause=%s sqlstate=%s", failure.cause_class, failure.sqlstate)
            await self._conversations.clear()
            await self._chat.send(settings_text.with_start_button(settings_text.SAVE_FAILED))

    # ---- the card and the questions ------------------------------------------------------------------------------

    async def _card(self, conversation: OpenConversation, note: str | None) -> None:
        """Move to the card at the stored version (new nonce) and show it."""
        stored = await self._store.read()
        moved = await self._conversations.advance(conversation.nonce, CARD, {"version": _version(stored)})
        if moved is not None:
            await self._show_card(moved.nonce, _policy(stored), note)

    async def _show_card(self, nonce: str, policy: TimePolicy, note: str | None) -> None:
        change = {key: button_data("set", nonce, key) for key in settings_text.VALUE_NAMES}
        await self._chat.send(settings_text.card(policy, change, note))

    async def _ask(self, conversation: OpenConversation, key: str) -> None:
        if key == settings_text.QUIET:
            await self._question(conversation, ASK_START, conversation.partial, settings_text.quiet_start_question())
        elif key in _SINGLE_TIME_FIELD:
            await self._question(conversation, key, conversation.partial, settings_text.time_question(key))
        elif key == settings_text.ZONE:  # the question arrives with U-quiet-hours-10
            await self._repeat(conversation, settings_text.ZONE_LATER)
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
        """Show the current step again, with the nonce the router just issued; ``lead`` explains why."""
        step = conversation.step
        if step == CONFLICT:
            await self._offer_again(conversation)
        elif step in _EXAMPLE:
            question = _question_text(conversation)
            text = f"{lead}\n\n{question}" if lead else question
            await self._chat.send(settings_text.with_cancel(text, button_data("cancel", conversation.nonce)))
        else:  # the card, or a step this dialogue does not know
            await self._show_card(conversation.nonce, _policy(await self._store.read()), lead)

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
            await self._repeat(conversation, settings_text.unreadable(text, _EXAMPLE[ASK_START]))
            return
        partial = {**conversation.partial, "start": settings_text.clock(start)}
        await self._question(conversation, ASK_END, partial, settings_text.quiet_end_question(start))

    async def _quiet_end(self, conversation: OpenConversation, text: str) -> None:
        end = parse_time(text)
        if end is None:
            await self._repeat(conversation, settings_text.unreadable(text, _EXAMPLE[ASK_END]))
            return
        start = _hhmm(conversation.partial["start"])
        await self._save(conversation, {"quiet_start": start, "quiet_end": end})

    # ---- storing -------------------------------------------------------------------------------------------------

    async def _current(self, conversation: OpenConversation) -> TimePolicy | None:
        """The stored policy if it is still at the version the card was shown at; else tell Marco and return None."""
        stored = await self._store.read()
        if _version(stored) != int(str(conversation.partial["version"])):
            await self._changed_elsewhere(conversation)
            return None
        return _policy(stored)

    async def _changed_elsewhere(self, conversation: OpenConversation) -> None:
        await self._card(conversation, settings_text.CHANGED_ELSEWHERE)

    async def _save(self, conversation: OpenConversation, changes: dict[str, time]) -> None:
        """Change some values of the stored policy as one whole new policy."""
        current = await self._current(conversation)
        if current is not None:
            await self._commit(conversation, replace(current, **changes))

    async def _commit(self, conversation: OpenConversation, proposed: TimePolicy) -> None:
        """Validate the whole policy, store it at the card's version and show the card again."""
        if problems := validate(proposed):
            await self._refuse(conversation, proposed, problems)
            return
        try:
            written = await self._store.write(proposed, int(str(conversation.partial["version"])), "telegram", self._by)
        except VersionConflict:
            await self._changed_elsewhere(conversation)
        except PolicyRefused as refused:  # unreachable after validate; kept so a refusal is never an error page
            await self._refuse(conversation, proposed, refused.problems)
        else:
            moved = await self._conversations.advance(conversation.nonce, CARD, {"version": written.version})
            if moved is not None:
                await self._show_card(moved.nonce, written.policy, SAVED)

    async def _refuse(self, conversation: OpenConversation, proposed: TimePolicy, problems: list[Problem]) -> None:
        """Say which rules the answer breaks and ask again (or offer the one-tap move); nothing is stored."""
        if conversation.step == ASK_END and all(problem.rule in _MOVED_FIELD for problem in problems):
            partial = {**conversation.partial, "end": settings_text.clock(proposed.quiet_end)}
            moved = await self._conversations.advance(conversation.nonce, CONFLICT, partial)
            if moved is not None:
                await self._send_offer(moved.nonce, proposed, problems)
            return
        lead = " ".join(settings_text.refusal(problem, proposed.window_minutes) for problem in problems)
        await self._repeat(conversation, lead)

    # ---- the one-tap move ----------------------------------------------------------------------------------------

    async def _send_offer(self, nonce: str, proposed: TimePolicy, problems: list[Problem]) -> None:
        offer = settings_text.move_offer(
            proposed, problems, button_data("set", nonce, MOVE), button_data("cancel", nonce)
        )
        await self._chat.send(offer)

    async def _with_new_window(self, conversation: OpenConversation) -> TimePolicy | None:
        """The stored policy with the quiet hours kept in the conversation; ``None`` if the row changed meanwhile."""
        current = await self._current(conversation)
        if current is None:
            return None
        partial = conversation.partial
        return replace(current, quiet_start=_hhmm(partial["start"]), quiet_end=_hhmm(partial["end"]))

    async def _offer_again(self, conversation: OpenConversation) -> None:
        proposed = await self._with_new_window(conversation)
        if proposed is not None:
            await self._send_offer(
                conversation.nonce, proposed, [p for p in validate(proposed) if p.rule in _MOVED_FIELD]
            )

    async def _move(self, conversation: OpenConversation) -> None:
        """Take the offer: move every trapped value to the quiet end and store everything in one write."""
        proposed = await self._with_new_window(conversation)
        if proposed is None:
            return
        moves = {_MOVED_FIELD[p.rule]: proposed.quiet_end for p in validate(proposed) if p.rule in _MOVED_FIELD}
        await self._commit(conversation, replace(proposed, **moves))
