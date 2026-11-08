"""Sending a reply that Marco has confirmed (spec AC-7, AC-16, AC-29; threat model T-02, T-15).

The reply goes to the ``From`` address of the original mail, in the same thread, and only when the original is a
normal mail from a person. A different ``Reply-To`` is ignored unless Marco names the address himself. Sending the same
draft twice never produces two mails. Like the read wrapper, this module has no operation that removes mail.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email.message import EmailMessage
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.adapters.gmail_read import FetchedMail

ME = "me"
SENT = "SENT"
NO_REPLY_NAMES = frozenset({"noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster"})
BULK_PRECEDENCE = frozenset({"bulk", "list", "junk"})


class NotRepliableError(Exception):
    """The original is an automatic, list or no-reply mail; no reply is created."""


class SenderMismatchError(Exception):
    """The draft names a sender other than the authenticated mailbox."""


@dataclass(frozen=True, slots=True)
class ConfirmedDraft:
    """A draft Marco has seen and confirmed. ``recipient`` is set only when Marco names another address."""

    draft_id: str
    sender: str
    recipient: str | None
    body: str


def _header(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("header value contains a line break")
    return value


def _check_repliable(original: FetchedMail) -> None:
    headers = original.headers
    auto = headers.get("Auto-Submitted")
    if auto is not None and auto.strip().lower() != "no":
        raise NotRepliableError("automatic mail")
    if "List-Id" in headers:
        raise NotRepliableError("mailing list")
    if headers.get("Precedence", "").strip().lower() in BULK_PRECEDENCE:
        raise NotRepliableError("bulk mail")
    if original.sender.split("@")[0].strip().lower() in NO_REPLY_NAMES:
        raise NotRepliableError("no-reply sender")


def _build(original: FetchedMail, draft: ConfirmedDraft) -> EmailMessage:
    message = EmailMessage()
    domain = draft.sender.rsplit("@", 1)[-1]
    subject = original.subject
    message["To"] = _header(draft.recipient or original.sender)
    message["From"] = _header(draft.sender)
    message["Subject"] = _header(subject if subject.lower().startswith("re:") else f"Re: {subject}")
    message["Message-ID"] = _header(f"<mail-triage-{draft.draft_id}@{domain}>")
    original_id = original.headers.get("Message-ID")
    if original_id:
        message["In-Reply-To"] = _header(original_id)
        message["References"] = _header(original_id)
    message.set_content(draft.body)
    return message


class GmailSender:
    """Send a confirmed reply. ``service`` is the Gmail v1 service."""

    def __init__(self, service: Any) -> None:  # noqa: ANN401
        """Keep the Gmail service."""
        self._service = service

    def send_reply(self, original: FetchedMail, draft: ConfirmedDraft) -> str:
        """Send ``draft`` as a reply to ``original`` and return the id of the sent mail."""
        _check_repliable(original)
        message = _build(original, draft)
        users = self._service.users()
        address = users.getProfile(userId=ME).execute()["emailAddress"]
        if address.casefold() != draft.sender.casefold():
            raise SenderMismatchError("the draft sender is not the authenticated mailbox")
        message_id = str(message["Message-ID"]).strip("<>")
        earlier = users.messages().list(userId=ME, q=f"rfc822msgid:{message_id}", labelIds=[SENT]).execute()
        if earlier.get("messages"):
            return str(earlier["messages"][0]["id"])
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {"raw": raw, "threadId": original.thread_id}
        return str(users.messages().send(userId=ME, body=body).execute()["id"])
