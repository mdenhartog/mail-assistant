"""Route Marco's commands, button presses and typed answers to the dialogues (spec C-8, AC-3 to AC-10; ADR-0026).

``CommandRouter`` is a thin registry. A registered ``DialogueHandler`` (the settings dialogue) owns a slash command and
the buttons and answers of its own conversation; the older snooze and reply questions keep their behaviour in
``QuestionFlows``. The router decides only who gets an update:

- A replayed Telegram update (same ``update_id``) is ignored; the memory of seen ids is bounded.
- Slash commands are handled before awaited text. Starting a dialogue replaces the stored conversation and says what
  was dropped.
- Text means something only while a question is pending; with none (or an expired one) Marco is pointed to the buttons.
- A handler is only ever called after the router has claimed the conversation with ``advance`` using the nonce of the
  button (or of the pending question for text). ``advance`` is atomic and rotates the nonce, so a double tap, or a tap
  and a text at once, reach the handler once; the loser finds the nonce stale and does nothing.

Who may talk to the agent is decided before this point, by the Telegram intake. Nothing here logs an answer, a nonce,
a token or a zone; rejections are logged by reason only.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from app.core.alert_state import AlertState

if TYPE_CHECKING:
    from app.adapters.telegram_inbox import Command
    from app.db.pg_conversation import Kind, OpenConversation
    from app.usecases.reply import StoredDraft

logger = logging.getLogger(__name__)

SNOOZE_HOURS = "snooze_hours"
REPLY_TEXT = "reply_text"
ASK_HOURS = "How many hours should I wait (1 to 168)? Or say 'tomorrow'."
USE_BUTTONS = "Use the buttons under an alert to reply, snooze or close it."
FINISH_FIRST = "Finish or cancel the settings question first."
OUT_OF_DATE = "That card is out of date."
CANCELLED = "Cancelled. Nothing was changed."
EXPIRED = "Expired"
EXPIRED_NOTE = "That question expired. Nothing was changed."
SETTINGS_TTL = timedelta(minutes=15)
SEEN_UPDATES_MAX = 1024
_ID = re.compile(r"[A-Za-z0-9-]{1,40}")
_TOKEN = re.compile(r"[0-9a-f]{16}")
_ARITY = {"reply": 1, "later": 1, "stop": 1, "edit": 1, "cancel": 1, "send": 2}

# Settings buttons: ASCII, at most 64 bytes, never a value. ``argument`` is a key or an index into stored candidates.
MAX_BUTTON_BYTES = 64
_NONCE = re.compile(r"[A-Za-z0-9_-]{22}")  # the 16-byte URL-safe token of the conversation store
_ARGUMENT = {"set": re.compile(r"[a-z][a-z_]{0,23}"), "tz": re.compile(r"[0-9]{1,2}"), "cancel": None, "undo": None}
_START = re.compile(r"start:([a-z]{1,16})")  # starts a dialogue like its slash command; carries no nonce and no value
_ASKS_FOR_TEXT = frozenset({"reply", "later", "edit"})
_SETTINGS_BUTTON = re.compile(r"(set|tz|cancel|undo):(?:([a-z0-9_]+):)?([A-Za-z0-9_-]+)")


class ReplyPort(Protocol):
    """The reply flow."""

    async def begin(self, alert_id: str) -> None:
        """Ask for the reply text."""
        ...

    async def start_reply(self, alert_id: str, text: str) -> None:
        """Make a draft from the text."""
        ...

    async def confirm(self, draft_id: str, token: str) -> None:
        """Send the draft."""
        ...

    async def edit(self, draft_id: str) -> None:
        """Drop the draft and wait for new text."""
        ...

    async def cancel(self, draft_id: str) -> None:
        """Cancel the draft."""
        ...


class SnoozePort(Protocol):
    """Snooze and close."""

    async def snooze(self, alert_id: str, answer: str) -> None:
        """Snooze for the typed hours or 'tomorrow'."""
        ...

    async def close(self, alert_id: str) -> None:
        """Close the alert."""
        ...


class RouterStore(Protocol):
    """What the snooze and reply questions remember and read."""

    async def set_awaiting(self, alert_id: str, kind: str | None) -> None:
        """Remember what Marco is asked to type for this alert."""
        ...

    async def awaiting(self) -> tuple[str, str] | None:
        """The alert and kind of input currently awaited."""
        ...

    async def state_of(self, alert_id: str) -> AlertState | None:
        """State of an alert."""
        ...

    async def get_draft(self, draft_id: str) -> StoredDraft | None:
        """A draft, to find the alert it belongs to."""
        ...


class ChatPort(Protocol):
    """Telegram, talking to Marco."""

    async def say(self, text: str) -> None:
        """A short plain note."""
        ...

    async def answer_callback(self, callback_id: str) -> None:
        """Stop the spinner on a pressed button."""
        ...

    async def edit_message(self, message_id: int, text: str) -> None:
        """Replace an earlier message's text and remove its buttons."""
        ...

    async def offer(self, text: str, label: str, data: str) -> None:
        """A short plain note with one button."""
        ...


class ConversationPort(Protocol):
    """The single stored conversation (``ConversationStore``)."""

    async def start(
        self, kind: Kind, target: str | None, step: str, partial: dict[str, object], ttl: timedelta | None
    ) -> OpenConversation:
        """Replace whatever is pending with a new dialogue."""
        ...

    async def current(self) -> OpenConversation | None:
        """The pending dialogue, or ``None`` when there is none or it has expired."""
        ...

    async def advance(self, nonce: str, step: str, partial: dict[str, object]) -> OpenConversation | None:
        """Atomically move on if ``nonce`` is the current one and alive; rotates the nonce."""
        ...

    async def clear(self) -> None:
        """Forget the pending dialogue."""
        ...


class DialogueHandler(Protocol):
    """A dialogue the router can start and feed (the settings dialogue).

    The router starts the conversation (``kind``, ``first_step``, ``ttl``) and calls ``begin`` with it. Every later
    call hands over the conversation after the router claimed it, so ``conversation.nonce`` is the fresh nonce for the
    next message; the handler puts it in the buttons it shows (``button_data``), moves on with ``advance`` or ends the
    dialogue with ``clear``. Cancel is handled by the router and never reaches the handler.
    """

    kind: Kind
    commands: frozenset[str]
    first_step: str
    ttl: timedelta | None

    async def begin(self, conversation: OpenConversation) -> None:
        """Show the first question."""
        ...

    async def on_text(self, conversation: OpenConversation, text: str) -> None:
        """Marco typed an answer."""
        ...

    async def on_button(self, conversation: OpenConversation, action: str, argument: str) -> None:
        """Marco tapped ``set``, ``tz`` or ``undo``; ``argument`` is the key or index (empty for ``undo``)."""
        ...


def button_data(action: str, nonce: str, argument: str | None = None) -> str:
    """Callback data of a settings button: ``set:<key>:<nonce>``, ``tz:<index>:<nonce>``, ``cancel:<nonce>``, ``undo:<nonce>``."""
    if action not in _ARGUMENT:
        raise ValueError("unknown settings button")
    pattern = _ARGUMENT[action]
    if (pattern is None) != (argument is None) or (pattern is not None and not pattern.fullmatch(argument or "")):
        raise ValueError("settings button argument is not a key or an index")
    if not _NONCE.fullmatch(nonce) or not nonce.isascii():
        raise ValueError("settings button nonce is malformed")
    data = ":".join(part for part in (action, argument, nonce) if part is not None)
    if len(data.encode("ascii")) > MAX_BUTTON_BYTES:
        raise ValueError("settings button is longer than the callback limit")
    return data


def _settings_button(data: str) -> tuple[str, str, str] | None:
    """Split settings callback data into (action, argument, nonce); ``None`` if it is not exactly one of the forms."""
    found = _SETTINGS_BUTTON.fullmatch(data)
    if found is None or not data.isascii():
        return None
    action, argument, nonce = found.group(1), found.group(2), found.group(3)
    pattern = _ARGUMENT[action]
    if (pattern is None) != (argument is None) or (pattern is not None and not pattern.fullmatch(argument or "")):
        return None
    if not _NONCE.fullmatch(nonce):
        return None
    return action, argument or "", nonce


def _parse(data: str) -> tuple[str, list[str]] | None:
    action, *args = data.split(":")
    if _ARITY.get(action) != len(args) or not all(_ID.fullmatch(arg) for arg in args):
        return None
    if action == "send" and not _TOKEN.fullmatch(args[1]):
        return None
    return action, args


class QuestionFlows:
    """The snooze and reply questions: buttons that ask for typed text, and the text that answers them."""

    def __init__(self, reply: ReplyPort, snooze: SnoozePort, store: RouterStore, chat: ChatPort) -> None:
        """Wire the use cases, the store and the chat."""
        self._reply = reply
        self._snooze = snooze
        self._store = store
        self._chat = chat

    async def run(self, action: str, args: list[str]) -> None:
        """Run one parsed snooze or reply button."""
        target = args[0]
        if action == "reply":
            await self._reply.begin(target)
            await self._store.set_awaiting(target, REPLY_TEXT)
        elif action == "later":
            await self._store.set_awaiting(target, SNOOZE_HOURS)
            await self._chat.say(ASK_HOURS)
        elif action == "stop":
            await self._snooze.close(target)
            await self._done_with(target)
        elif action == "edit":
            await self._reply.edit(target)
            await self._awaiting_for_draft(target, REPLY_TEXT)
        elif action == "send":
            await self._reply.confirm(target, args[1])
            await self._awaiting_for_draft(target, None)
        elif action == "cancel":
            await self._reply.cancel(target)
            await self._awaiting_for_draft(target, None)

    async def _awaiting_for_draft(self, draft_id: str, kind: str | None) -> None:
        draft = await self._store.get_draft(draft_id)
        if draft is not None:
            await self._store.set_awaiting(draft.alert_id, kind)

    async def _done_with(self, alert_id: str) -> None:
        waiting = await self._store.awaiting()
        if waiting is not None and waiting[0] == alert_id:
            await self._store.set_awaiting(alert_id, None)

    async def text(self, text: str) -> None:
        """Read typed text as the answer to the awaited snooze or reply question."""
        waiting = await self._store.awaiting()
        if waiting is None:
            await self._chat.say(USE_BUTTONS)
            return
        alert_id, kind = waiting
        if kind == SNOOZE_HOURS:
            await self._snooze.snooze(alert_id, text)
            if await self._store.state_of(alert_id) is AlertState.SNOOZED:
                await self._store.set_awaiting(alert_id, None)
        elif kind == REPLY_TEXT:
            await self._reply.start_reply(alert_id, text)


def _dropped(conversation: OpenConversation) -> str:
    if conversation.target is not None:
        return f"I dropped the question about alert {conversation.target}."
    return f"I dropped the open {conversation.kind} question."


class CommandRouter:
    """Hands each update to the right dialogue."""

    def __init__(  # noqa: PLR0913, PLR0917 - the use cases, store, chat and conversation are all injected
        self,
        reply: ReplyPort,
        snooze: SnoozePort,
        store: RouterStore,
        chat: ChatPort,
        conversations: ConversationPort,
    ) -> None:
        """Wire the snooze and reply flows, the chat and the stored conversation."""
        self._flows = QuestionFlows(reply, snooze, store, chat)
        self._chat = chat
        self._conversations = conversations
        self._handlers: dict[str, DialogueHandler] = {}
        self._commands: dict[str, DialogueHandler] = {}
        self._seen: OrderedDict[int, None] = OrderedDict()

    def register(self, handler: DialogueHandler) -> None:
        """Add a dialogue: its slash commands start it, and its conversation kind routes buttons and text to it."""
        self._handlers[handler.kind] = handler
        self._commands.update(dict.fromkeys(handler.commands, handler))

    async def handle(self, command: Command) -> None:
        """Run one update, once."""
        if not self._first_time(command.update_id):
            return
        if command.kind == "text":
            await self._text(command.data)
            return
        if command.callback_id:
            await self._chat.answer_callback(command.callback_id)
        await self._button(command)

    def _first_time(self, update_id: int) -> bool:
        if update_id in self._seen:
            return False
        self._seen[update_id] = None
        if len(self._seen) > SEEN_UPDATES_MAX:
            self._seen.popitem(last=False)
        return True

    async def _start(self, handler: DialogueHandler) -> None:
        previous = await self._conversations.current()
        if previous is not None:
            await self._chat.say(_dropped(previous))
        started = await self._conversations.start(handler.kind, None, handler.first_step, {}, handler.ttl)
        await handler.begin(started)

    async def _claim(self, current: OpenConversation) -> OpenConversation | None:
        """Take this turn of the conversation; ``None`` if another update took it first."""
        return await self._conversations.advance(current.nonce, current.step, current.partial)

    async def _text(self, text: str) -> None:
        handler = self._commands.get(text.split(maxsplit=1)[0].split("@")[0].lower()) if text.startswith("/") else None
        if handler is not None:
            await self._start(handler)
            return
        current = await self._conversations.current()
        owner = self._handlers.get(current.kind) if current is not None else None
        if current is None or owner is None:
            await self._flows.text(text)
            return
        claimed = await self._claim(current)
        if claimed is not None:
            await owner.on_text(claimed, text)

    async def _button(self, command: Command) -> None:
        started = _START.fullmatch(command.data)
        if started is not None:
            handler = self._handlers.get(started.group(1))
            if handler is not None:
                await self._start(handler)
            return
        parsed = _settings_button(command.data)
        if parsed is not None:
            await self._settings_button(command, *parsed)
            return
        question = _parse(command.data)
        if question is None:
            return
        if question[0] in _ASKS_FOR_TEXT and await self._settings_pending():
            await self._chat.say(FINISH_FIRST)  # an older question must not replace the settings question
            return
        await self._flows.run(*question)

    async def _settings_pending(self) -> bool:
        current = await self._conversations.current()
        return current is not None and current.kind in self._handlers

    async def _settings_button(self, command: Command, action: str, argument: str, nonce: str) -> None:
        handler = self._handlers.get("settings")
        if handler is None:
            return
        current = await self._conversations.current()
        if current is None:  # no live question: it expired (or was closed); the card loses its buttons
            logger.info("dialogue button rejected reason=expired")
            await self._chat.edit_message(command.message_id, EXPIRED)
            await self._chat.offer(EXPIRED_NOTE, "Start again", f"start:{handler.kind}")
            return
        claimed = await self._claim(current) if current.kind == handler.kind and current.nonce == nonce else None
        if claimed is None:
            logger.info("dialogue button rejected reason=stale")
            await self._chat.offer(OUT_OF_DATE, "Show settings", f"start:{handler.kind}")
        elif action == "cancel":
            await self._conversations.clear()
            await self._chat.edit_message(command.message_id, CANCELLED)
        else:
            await handler.on_button(claimed, action, argument)
