"""Reply flow with confirmation: nothing is sent until Marco has seen the exact text and pressed Send.

Spec AC-6, AC-7, AC-8, AC-16, AC-17, AC-20, AC-22, AC-29. A draft is stored with a digest over recipient, subject and
body. The Send button carries the draft id and the start of that digest. Confirming checks the token, recomputes the
digest from the stored text, and consumes the draft in one atomic step, so a replayed, expired, edited or foreign
confirmation sends nothing. Audit entries carry ids and the digest, never the text.
"""

from __future__ import annotations

import asyncio
import hmac
import html
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from app.adapters.gmail_send import ConfirmedDraft, NotRepliableError
from app.core.alert_state import AlertState, Event, InvalidTransitionError, transition
from app.core.alert_text import AlertMessage, Button
from app.db.repos import digest_of

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail

DRAFT_TTL = timedelta(minutes=15)
MAX_BODY_CHARS = 3000
TOKEN_CHARS = 16
NOT_OPEN = "That alert is no longer open."
INVALID = "This confirmation is no longer valid. Nothing was sent."
_TO_LINE = re.compile(r"^to:[ \t]*(?P<address>[^\r\n]*)(?:\r?\n|$)", re.IGNORECASE)
_ADDRESS = re.compile(r"[^@\s<>,;\"'()\[\]]+@[^@\s<>,;\"'()\[\]]+\.[^@\s<>,;\"'()\[\]]+")
_REPLYABLE = {AlertState.OPEN, AlertState.DRAFTING, AlertState.CONFIRMING}


@dataclass(frozen=True, slots=True)
class AlertInfo:
    """What the reply flow needs to know about an alert."""

    state: AlertState
    gmail_message_id: str


@dataclass(frozen=True, slots=True)
class StoredDraft:
    """A draft waiting for confirmation. ``recipient`` is ``None`` unless Marco named another address."""

    draft_id: str
    alert_id: str
    recipient: str | None
    body: str
    digest: str
    expires_at: datetime
    used: bool


class ReplyStore(Protocol):
    """Persistence for the reply flow."""

    async def alert_info(self, alert_id: str) -> AlertInfo | None:
        """State and Gmail message id of an alert, or ``None``."""
        ...

    async def set_state(self, alert_id: str, state: AlertState) -> None:
        """Save the alert state."""
        ...

    async def save_draft(self, draft: StoredDraft) -> None:
        """Store a draft."""
        ...

    async def get_draft(self, draft_id: str) -> StoredDraft | None:
        """Read a draft."""
        ...

    async def consume_draft(self, draft_id: str, digest: str, *, now: datetime) -> StoredDraft | None:
        """Atomically mark a draft used if it is unused, unexpired and matches the digest."""
        ...

    async def invalidate_drafts(self, alert_id: str) -> None:
        """Mark every draft of the alert as used, so no old confirmation works."""
        ...

    async def record_audit(self, kind: str, alert_id: str, digest: str | None = None) -> None:
        """Write an audit entry: kind, alert id and digest only."""
        ...


class Mailbox(Protocol):
    """Gmail read access (blocking)."""

    def fetch(self, message_id: str) -> FetchedMail:
        """Headers and text of one mail."""
        ...


class Sender(Protocol):
    """Gmail send access (blocking)."""

    def check_repliable(self, original: FetchedMail) -> None:
        """Raise ``NotRepliableError`` when no reply may be created."""
        ...

    def send_reply(self, original: FetchedMail, draft: ConfirmedDraft) -> str:
        """Send the reply in the same thread and return the sent message id."""
        ...


class Chat(Protocol):
    """Telegram, talking to Marco."""

    async def send(self, message: AlertMessage) -> int:
        """Send a message with buttons; return its id."""
        ...

    async def say(self, text: str) -> None:
        """Send a short plain message."""
        ...


def _split_recipient(text: str) -> tuple[str | None, str] | None:
    """Optional ``To:`` first line. ``None`` means the line is there but is not one valid address."""
    match = _TO_LINE.match(text)
    if match is None:
        return None, text
    address = match.group("address").strip()
    if not _ADDRESS.fullmatch(address):
        return None
    return address.casefold(), text[match.end() :].strip()


class ReplyService:
    """The reply commands behind the Reply, Send, Edit and Cancel buttons."""

    def __init__(  # noqa: PLR0913 - every dependency is injected for tests
        self,
        store: ReplyStore,
        mailbox: Mailbox,
        sender: Sender,
        chat: Chat,
        *,
        own_address: str,
        now: Callable[[], datetime],
        new_id: Callable[[], str],
    ) -> None:
        """Wire the ports, the authenticated mailbox address, the clock and the draft id source."""
        self._store = store
        self._mail = mailbox
        self._sender = sender
        self._chat = chat
        self._own = own_address
        self._now = now
        self._new_id = new_id

    async def begin(self, alert_id: str) -> None:
        """The Reply button: ask Marco to type his answer."""
        info = await self._store.alert_info(alert_id)
        if info is None or info.state is not AlertState.OPEN:
            await self._chat.say(NOT_OPEN)
            return
        await self._store.set_state(alert_id, transition(info.state, Event.START_DRAFT))
        await self._chat.say("Type your reply. Start with 'To: name@example.com' to answer someone else.")

    async def start_reply(self, alert_id: str, text: str) -> None:
        """Turn Marco's text into a draft and show it with Send, Edit and Cancel. Sends nothing."""
        info = await self._store.alert_info(alert_id)
        if info is None or info.state not in _REPLYABLE:
            await self._chat.say(NOT_OPEN)
            return
        parsed = _split_recipient(text.strip())
        if parsed is None:
            await self._chat.say("I could not read that address. Use one address, like: To: name@example.com")
            return
        recipient, body = parsed
        problem = self._problem_with(body)
        if problem:
            await self._chat.say(problem)
            return
        original = await asyncio.to_thread(self._mail.fetch, info.gmail_message_id)
        try:
            await asyncio.to_thread(self._sender.check_repliable, original)
        except NotRepliableError:
            await self._chat.say("This mail cannot be replied to (it is automatic or from a list).")
            return
        await self._show(alert_id, info, original, recipient, body)

    @staticmethod
    def _problem_with(body: str) -> str | None:
        if not body:
            return "The reply is empty. Type the text you want to send."
        if len(body) > MAX_BODY_CHARS:
            return f"The reply is too long (at most {MAX_BODY_CHARS} characters)."
        return None

    async def _show(
        self, alert_id: str, info: AlertInfo, original: FetchedMail, recipient: str | None, body: str
    ) -> None:
        await self._store.invalidate_drafts(alert_id)  # an older confirmation must not work any more
        state = info.state
        if state is not AlertState.DRAFTING:
            state = transition(state, Event.START_DRAFT)
        confirming = transition(state, Event.SHOW_DRAFT)
        digest = digest_of(recipient or original.sender, original.subject, body)
        draft = StoredDraft(
            draft_id=self._new_id(),
            alert_id=alert_id,
            recipient=recipient,
            body=body,
            digest=digest,
            expires_at=self._now() + DRAFT_TTL,
            used=False,
        )
        await self._store.save_draft(draft)
        await self._store.set_state(alert_id, confirming)
        await self._store.record_audit("reply_drafted", alert_id, digest)
        await self._chat.send(self._preview(draft, original))

    @staticmethod
    def _preview(draft: StoredDraft, original: FetchedMail) -> AlertMessage:
        subject = original.subject if original.subject.lower().startswith("re:") else f"Re: {original.subject}"
        text = "\n".join(
            [
                "<b>Draft reply - nothing is sent yet</b>",
                f"<b>To:</b> {html.escape(draft.recipient or original.sender, quote=False)}",
                f"<b>Subject:</b> {html.escape(subject[:150], quote=False)}",
                "",
                html.escape(draft.body, quote=False),
            ]
        )
        token = draft.digest[:TOKEN_CHARS]
        buttons = (
            Button("Send", f"send:{draft.draft_id}:{token}"),
            Button("Edit", f"edit:{draft.draft_id}"),
            Button("Cancel", f"cancel:{draft.draft_id}"),
        )
        return AlertMessage(text=text, buttons=buttons)

    async def confirm(self, draft_id: str, token: str) -> None:
        """The Send button: send the stored text once, to the stored recipient, in the original thread."""
        draft = await self._store.get_draft(draft_id)
        info = await self._store.alert_info(draft.alert_id) if draft else None
        if draft is None or info is None or info.state is not AlertState.CONFIRMING or draft.used:
            await self._chat.say(INVALID)
            return
        original = await asyncio.to_thread(self._mail.fetch, info.gmail_message_id)
        intact = digest_of(draft.recipient or original.sender, original.subject, draft.body) == draft.digest
        if not (intact and hmac.compare_digest(token, draft.digest[:TOKEN_CHARS])):
            await self._chat.say(INVALID)
            return
        if await self._store.consume_draft(draft_id, draft.digest, now=self._now()) is None:
            await self._chat.say(INVALID)
            return
        await self._send(draft, original)

    async def _send(self, draft: StoredDraft, original: FetchedMail) -> None:
        confirmed = ConfirmedDraft(
            draft_id=draft.draft_id, sender=self._own, recipient=draft.recipient, body=draft.body
        )
        try:
            await asyncio.to_thread(self._sender.send_reply, original, confirmed)
        except Exception:
            await self._store.record_audit("reply_failed", draft.alert_id, draft.digest)
            await self._chat.say("The reply could not be sent. Press Edit on the draft to try again.")
            return
        await self._store.set_state(draft.alert_id, transition(AlertState.CONFIRMING, Event.SENT))
        await self._store.record_audit("reply_sent", draft.alert_id, draft.digest)
        await self._chat.say("Reply sent.")

    async def edit(self, draft_id: str) -> None:
        """The Edit button: drop the draft and wait for new text."""
        draft = await self._store.get_draft(draft_id)
        info = await self._store.alert_info(draft.alert_id) if draft else None
        if draft is None or info is None or info.state is not AlertState.CONFIRMING:
            await self._chat.say(NOT_OPEN)
            return
        await self._store.invalidate_drafts(draft.alert_id)
        await self._store.set_state(draft.alert_id, transition(info.state, Event.START_DRAFT))
        await self._store.record_audit("reply_edit_started", draft.alert_id, draft.digest)
        await self._chat.say("Type the new reply text.")

    async def cancel(self, draft_id: str) -> None:
        """The Cancel button: nothing is sent and the alert is open again."""
        draft = await self._store.get_draft(draft_id)
        info = await self._store.alert_info(draft.alert_id) if draft else None
        try:
            if draft is None or info is None:
                raise InvalidTransitionError
            reopened = transition(info.state, Event.CANCEL_DRAFT)
        except InvalidTransitionError:
            await self._chat.say(NOT_OPEN)
            return
        await self._store.invalidate_drafts(draft.alert_id)
        await self._store.set_state(draft.alert_id, reopened)
        await self._store.record_audit("reply_cancelled", draft.alert_id, draft.digest)
        await self._chat.say("Cancelled. Nothing was sent.")
