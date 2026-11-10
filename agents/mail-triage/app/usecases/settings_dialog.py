"""The settings dialogue (spec C-2, C-3, C-8; Behaviour 1 to 5; ADR-0025, ADR-0026).

``SettingsDialog`` is a ``DialogueHandler`` of kind ``settings``. The router starts the conversation, claims every
button and answer (rotating the nonce) and handles Cancel; this class decides what to ask and what to store.

Every write is the WHOLE new policy through ``SettingsStore.write`` with the version the card was shown at, so a change
made elsewhere meanwhile is a ``VersionConflict`` and never overwritten. Nothing here logs a typed answer, a nonce, a
token or a zone: failures are logged by class and SQLSTATE only.

The time zone question (spec C-6): Marco types a city or a country; ``places.lookup`` (with the injected clock's
``now``) finds the zone. One hit is stored; several hits, a country with several zones or a near miss become buttons
``tz:<index>:<nonce>`` whose index points into the candidates kept in the conversation's ``partial``, never a zone name.
Text that cannot be a place name is refused before the lookup is called.

When the stored row is invalid (a zone the tz database dropped, a value an operator emptied), ``/settings`` still opens:
the card shows the values in use (the policy source's last good values or the defaults) under a note, and the first
valid answer writes a whole new row over the invalid one at the version the card was shown at (RT-1).

After every write ``Confirmation`` (settings_confirm.py) sends the full picture with an Undo button and keeps the Undo
in a long-lived conversation of step ``undo``; the button "Show settings" brings the card back.
"""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import time
from typing import TYPE_CHECKING, ClassVar, Protocol

from app.core import settings_text
from app.db.repos import PolicyRefused, SettingsStoreFailure, VersionConflict
from app.usecases.dispatch import SETTINGS_TTL, UNDO_STEP, button_data
from app.usecases.settings_confirm import Confirmation
from schedule_policy.parse import parse_time
from schedule_policy.places import MAX_TEXT_LENGTH, lookup
from schedule_policy.policy import DEFAULT_POLICY, validate

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from datetime import datetime, timedelta

    from app.core.alert_text import AlertMessage
    from app.db.pg_conversation import Kind, OpenConversation
    from app.db.repos import SettingsStore, SettingsView
    from app.usecases.dispatch import ConversationPort
    from schedule_policy.places import PlaceHit
    from schedule_policy.policy import Problem, TimePolicy

logger = logging.getLogger(__name__)

CARD = "card"
ASK_START = "quiet_start"
ASK_END = "quiet_end"
CONFLICT = "conflict"
ASK_ZONE = "zone"
PICK_ZONE = "zone_pick"
OVERVIEW = settings_text.OVERVIEW
REMIND = settings_text.REMIND
MOVE = "move"
_SINGLE_TIME_FIELD = {OVERVIEW: "overview_at", REMIND: "remind_at"}
_MOVED_FIELD = {"overview_in_quiet_hours": "overview_at", "remind_in_quiet_hours": "remind_at"}
_EXAMPLE = {ASK_START: "23:00", ASK_END: "07:00", OVERVIEW: "18:00", REMIND: "09:00"}
# Text that may be a place name: starts with a letter, then letters, digits, spaces and . ' / + - _ (IANA names).
_PLACE = re.compile("[^\\W\\d_][\\w .'\\u2019/+-]*")


class DialogChat(Protocol):
    """What the dialogue needs from Telegram: a message with buttons."""

    async def send(self, message: AlertMessage) -> int:
        """Send a message with its buttons; return the Telegram message id."""
        ...


def _parse_clock(value: object) -> time:
    """A clock time kept in a conversation's ``partial`` as ``HH:MM`` text."""
    hour, minute = str(value).split(":")
    return time(int(hour), int(minute))


def _question_text(conversation: OpenConversation) -> str:
    """The question of the conversation's current step."""
    if conversation.step == ASK_START:
        return settings_text.quiet_start_question()
    if conversation.step == ASK_END:
        return settings_text.quiet_end_question(_parse_clock(conversation.partial["start"]))
    if conversation.step == ASK_ZONE:
        return settings_text.ZONE_QUESTION
    return settings_text.time_question(conversation.step)


def _place_text(text: str) -> str | None:
    """The trimmed text if it can be a place name (short, letter first, no ``..``, no control characters)."""
    trimmed = text.strip()
    if not trimmed or len(trimmed) > MAX_TEXT_LENGTH or ".." in trimmed or not _PLACE.fullmatch(trimmed):
        return None
    return trimmed


def _choices(conversation: OpenConversation) -> tuple[list[str], list[str]]:
    """The candidate zones and their labels kept in the conversation (empty when there are none)."""
    zones, labels = conversation.partial.get("zones"), conversation.partial.get("labels")
    if not isinstance(zones, list) or not isinstance(labels, list) or len(zones) != len(labels):
        return [], []
    return [str(zone) for zone in zones], [str(label) for label in labels]


def _note(view: SettingsView, note: str | None) -> str | None:
    """``note`` plus the line that says the saved settings are invalid, when they are."""
    if not view.invalid:
        return note
    return f"{note} {settings_text.INVALID_SAVED}" if note else settings_text.INVALID_SAVED


class SettingsDialog:
    """Shows the settings card and asks the questions behind its Change buttons."""

    kind: ClassVar[Kind] = "settings"
    commands: ClassVar[frozenset[str]] = frozenset({"/settings"})
    first_step: ClassVar[str] = CARD
    ttl: ClassVar[timedelta | None] = SETTINGS_TTL

    def __init__(  # noqa: PLR0913, PLR0917 - every collaborator is injected, nothing is read from the environment
        self,
        store: SettingsStore,
        chat: DialogChat,
        conversations: ConversationPort,
        allowed_user_id: int,
        now: Callable[[], datetime],
        in_use: Callable[[], TimePolicy],
    ) -> None:
        """Wire the settings store, Telegram, the stored conversation, the one user, a clock and the values in use.

        ``in_use`` gives the policy the agent works with while the stored row is invalid (the policy source's last good
        values or the defaults); it must not read the database or send a notice.
        """
        self._store = store
        self._chat = chat
        self._conversations = conversations
        self._by = str(allowed_user_id)
        self._now = now
        self._in_use = in_use
        self._confirmation = Confirmation(store, chat, conversations, self._by, now)

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
            elif step in {ASK_ZONE, PICK_ZONE}:
                await self._zone_text(conversation, text)
            else:
                await self._repeat(conversation, settings_text.TAP_A_BUTTON if step == CARD else None)

    async def on_button(self, conversation: OpenConversation, action: str, argument: str) -> None:
        """Marco tapped a button."""
        async with self._guard():
            if action == "set" and conversation.step == CARD:
                await self._ask(conversation, argument)
            elif action == "set" and conversation.step == CONFLICT and argument == MOVE:
                await self._move(conversation)
            elif action == "tz" and conversation.step == PICK_ZONE:
                await self._zone_button(conversation, argument)
            elif action == "undo" and conversation.step == UNDO_STEP:
                await self._confirmation.undo(conversation)
            else:
                await self._repeat(conversation)

    @asynccontextmanager
    async def _guard(self) -> AsyncGenerator[None]:
        """A store failure ends the dialogue with an honest note; nothing was written by the failed call."""
        try:
            yield
        except SettingsStoreFailure as failure:
            logger.warning("settings store failed cause=%s sqlstate=%s", failure.cause_class, failure.sqlstate)
            await self._end_with_failure_note()
        except OSError as failure:  # a refused connection can reach ``read`` unwrapped; log the class only
            logger.warning("settings store unreachable cause=%s", type(failure).__name__)
            await self._end_with_failure_note()

    async def _end_with_failure_note(self) -> None:
        await self._conversations.clear()
        await self._chat.send(settings_text.with_start_button(settings_text.SAVE_FAILED))

    # ---- the card and the questions ------------------------------------------------------------------------------

    async def _card(self, conversation: OpenConversation, note: str | None) -> None:
        """Move to the card at the stored version (new nonce) and show it."""
        view = await self._store.read_for_dialogue()
        moved = await self._conversations.advance(conversation.nonce, CARD, {"version": view.version})
        if moved is not None:
            await self._show_card(moved.nonce, self._shown(view), _note(view, note))

    def _shown(self, view: SettingsView) -> TimePolicy:
        """The policy a card shows and a change starts from: the stored one, else what is in use, else the defaults."""
        if view.policy is not None:
            return view.policy
        return self._in_use() if view.invalid else DEFAULT_POLICY

    async def _show_card(self, nonce: str, policy: TimePolicy, note: str | None) -> None:
        change = {key: button_data("set", nonce, key) for key in settings_text.VALUE_NAMES}
        await self._chat.send(settings_text.card(policy, change, note))

    async def _ask(self, conversation: OpenConversation, key: str) -> None:
        if key == settings_text.QUIET:
            await self._question(conversation, ASK_START, conversation.partial, settings_text.quiet_start_question())
        elif key in _SINGLE_TIME_FIELD:
            await self._question(conversation, key, conversation.partial, settings_text.time_question(key))
        elif key == settings_text.ZONE:
            await self._question(conversation, ASK_ZONE, conversation.partial, settings_text.ZONE_QUESTION)
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
        elif step == UNDO_STEP:
            await self._confirmation.offer_again(conversation)
        elif step == PICK_ZONE and _choices(conversation)[0]:
            await self._send_choices(conversation.nonce, conversation, lead or settings_text.ZONE_TAP_ONE)
        elif step in _EXAMPLE or step in {ASK_ZONE, PICK_ZONE}:
            question = _question_text(conversation)
            text = f"{lead}\n\n{question}" if lead else question
            await self._chat.send(settings_text.with_cancel(text, button_data("cancel", conversation.nonce)))
        else:  # the card, or a step this dialogue does not know
            view = await self._store.read_for_dialogue()
            await self._show_card(conversation.nonce, self._shown(view), _note(view, lead))

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
        start = _parse_clock(conversation.partial["start"])
        await self._save(conversation, {"quiet_start": start, "quiet_end": end})

    async def _zone_text(self, conversation: OpenConversation, text: str) -> None:
        """Look the typed place up; the lookup is only called with text that can be a place name."""
        place = _place_text(text)
        if place is None:
            await self._ask_zone_again(conversation, settings_text.ZONE_NOT_A_PLACE)
            return
        found = lookup(place, now=self._now())
        if len(found.hits) == 1:
            await self._save(conversation, {"zone": found.hits[0].zone})
        elif found.hits:
            await self._offer_zones(conversation, found.hits, settings_text.ZONE_CHOOSE)
        elif found.suggestion is not None and (close := lookup(found.suggestion, now=self._now()).hits):
            await self._offer_zones(conversation, close, settings_text.did_you_mean(found.suggestion))
        else:
            await self._ask_zone_again(conversation, settings_text.ZONE_NOT_FOUND)

    async def _ask_zone_again(self, conversation: OpenConversation, lead: str) -> None:
        """Say why the answer did not work and ask for the place again (the zone question, with Cancel)."""
        partial = {"version": conversation.partial["version"]}
        await self._question(conversation, ASK_ZONE, partial, f"{lead}\n\n{settings_text.ZONE_QUESTION}")

    async def _offer_zones(self, conversation: OpenConversation, hits: tuple[PlaceHit, ...], text: str) -> None:
        """Keep the candidates in the conversation and show one button per candidate (the index, never the zone)."""
        partial = {
            "version": conversation.partial["version"],
            "zones": [hit.zone for hit in hits],
            "labels": [hit.label for hit in hits],
        }
        moved = await self._conversations.advance(conversation.nonce, PICK_ZONE, partial)
        if moved is not None:
            await self._send_choices(moved.nonce, moved, text)

    async def _send_choices(self, nonce: str, conversation: OpenConversation, text: str) -> None:
        labels = _choices(conversation)[1]
        choices = [(label, button_data("tz", nonce, str(index))) for index, label in enumerate(labels)]
        await self._chat.send(settings_text.with_choices(text, choices, button_data("cancel", nonce)))

    async def _zone_button(self, conversation: OpenConversation, argument: str) -> None:
        """Store the candidate the button points to; an index outside the candidates changes nothing."""
        zones = _choices(conversation)[0]
        index = int(argument) if argument.isdecimal() else -1
        if 0 <= index < len(zones):
            await self._save(conversation, {"zone": zones[index]})
        else:
            await self._repeat(conversation, settings_text.ZONE_TAP_ONE)

    # ---- storing -------------------------------------------------------------------------------------------------

    async def _current(self, conversation: OpenConversation) -> TimePolicy | None:
        """The policy to change if the row is still at the version the card was shown at; else tell Marco, return None.

        An invalid row counts as at its version: the policy returned is then the one in use, and the write replaces it.
        """
        view = await self._store.read_for_dialogue()
        if view.version != int(str(conversation.partial["version"])):
            await self._changed_elsewhere(conversation)
            return None
        return self._shown(view)

    async def _changed_elsewhere(self, conversation: OpenConversation) -> None:
        await self._card(conversation, settings_text.CHANGED_ELSEWHERE)

    async def _save(self, conversation: OpenConversation, changes: dict[str, time | str]) -> None:
        """Change some values of the stored policy as one whole new policy."""
        current = await self._current(conversation)
        if current is not None:
            await self._commit(conversation, current, replace(current, **changes))

    async def _commit(self, conversation: OpenConversation, previous: TimePolicy, proposed: TimePolicy) -> None:
        """Validate the whole policy, store it at the card's version and confirm it with the full picture."""
        if problems := validate(proposed):
            await self._refuse(conversation, proposed, problems)
            return
        try:
            written = await self._store.write(proposed, int(str(conversation.partial["version"])), "telegram", self._by)
        except VersionConflict:
            await self._changed_elsewhere(conversation)
        except PolicyRefused as refused:  # the store validates again; a skew between the two is a refusal, not a crash
            await self._refuse(conversation, proposed, refused.problems)
        else:
            await self._confirmation.confirm(settings_text.SAVED, previous, written)

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

    async def _with_new_window(self, conversation: OpenConversation) -> tuple[TimePolicy, TimePolicy] | None:
        """The stored policy and the same with the quiet hours kept in the conversation; ``None`` if the row changed."""
        current = await self._current(conversation)
        if current is None:
            return None
        partial = conversation.partial
        return current, replace(
            current, quiet_start=_parse_clock(partial["start"]), quiet_end=_parse_clock(partial["end"])
        )

    async def _offer_again(self, conversation: OpenConversation) -> None:
        both = await self._with_new_window(conversation)
        if both is not None:
            proposed = both[1]
            await self._send_offer(
                conversation.nonce, proposed, [p for p in validate(proposed) if p.rule in _MOVED_FIELD]
            )

    async def _move(self, conversation: OpenConversation) -> None:
        """Take the offer: move every trapped value to the quiet end and store everything in one write."""
        both = await self._with_new_window(conversation)
        if both is None:
            return
        previous, proposed = both
        moves = {_MOVED_FIELD[p.rule]: proposed.quiet_end for p in validate(proposed) if p.rule in _MOVED_FIELD}
        await self._commit(conversation, previous, replace(proposed, **moves))
