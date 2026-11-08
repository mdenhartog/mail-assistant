"""Route Marco's button presses and typed answers to the use cases (spec AC-6 to AC-10).

Button data is ``<action>:<id>`` (``send`` also carries a token). It is parsed strictly; anything else does nothing. A
typed text means something only while the agent is waiting for it (hours for a snooze, or the text of a reply); the
store remembers what is awaited, so a restart does not lose the conversation. Who may talk to the agent is decided
before this point, by the Telegram intake.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

from app.core.alert_state import AlertState

if TYPE_CHECKING:
    from app.adapters.telegram_inbox import Command
    from app.usecases.reply import StoredDraft

SNOOZE_HOURS = "snooze_hours"
REPLY_TEXT = "reply_text"
ASK_HOURS = "How many hours should I wait (1 to 168)? Or say 'tomorrow'."
USE_BUTTONS = "Use the buttons under an alert to reply, snooze or close it."
_ID = re.compile(r"[A-Za-z0-9-]{1,40}")
_TOKEN = re.compile(r"[0-9a-f]{16}")
_ARITY = {"reply": 1, "later": 1, "stop": 1, "edit": 1, "cancel": 1, "send": 2}


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
    """What the router remembers and reads."""

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


def _parse(data: str) -> tuple[str, list[str]] | None:
    action, *args = data.split(":")
    if _ARITY.get(action) != len(args) or not all(_ID.fullmatch(arg) for arg in args):
        return None
    if action == "send" and not _TOKEN.fullmatch(args[1]):
        return None
    return action, args


class CommandRouter:
    """Turns a ``Command`` into a call on the right use case."""

    def __init__(self, reply: ReplyPort, snooze: SnoozePort, store: RouterStore, chat: ChatPort) -> None:
        """Wire the use cases, the store and the chat."""
        self._reply = reply
        self._snooze = snooze
        self._store = store
        self._chat = chat

    async def handle(self, command: Command) -> None:
        """Run one command."""
        if command.kind == "text":
            await self._text(command.data)
            return
        if command.callback_id:
            await self._chat.answer_callback(command.callback_id)
        parsed = _parse(command.data)
        if parsed is not None:
            await self._button(*parsed)

    async def _button(self, action: str, args: list[str]) -> None:
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

    async def _text(self, text: str) -> None:
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
