"""The text Marco sees in Telegram, and its buttons (spec AC-3, AC-16, AC-21, AC-23).

Mail content is untrusted. Every mail-derived string is length-capped and HTML-escaped; the only tags in a message are
the labels written here, so mail text can neither add markup nor make a masked link. Attachments are never described
beyond the fact that one exists.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from email.utils import parseaddr
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.judgement import Judgement

MAX_MESSAGE_CHARS = 4096  # Telegram's limit for one message
SENDER_CHARS = 120
SUBJECT_CHARS = 150
REASON_CHARS = 200
SUMMARY_CHARS = 400
DIGEST_LISTED = 20
DIGEST_SENDER_CHARS = 60
DIGEST_SUBJECT_CHARS = 80
BUTTON_DATA_MAX = 64
_FAILED = frozenset({"fail", "softfail", "permerror", "temperror"})


@dataclass(frozen=True, slots=True)
class MailMeta:
    """The facts about a mail that an alert may show."""

    sender: str
    subject: str
    reply_to: str | None
    has_attachment: bool


@dataclass(frozen=True, slots=True)
class AuthResults:
    """Results of SPF, DKIM and DMARC from the receiving server's ``Authentication-Results`` (``None`` when absent)."""

    spf: str | None
    dkim: str | None
    dmarc: str | None


@dataclass(frozen=True, slots=True)
class Button:
    """An inline keyboard button; ``data`` is the callback payload ``<action>:<alert id>``."""

    label: str
    data: str


@dataclass(frozen=True, slots=True)
class AlertMessage:
    """What to send: HTML text (escaped by this module) and the buttons below it."""

    text: str
    buttons: tuple[Button, ...]
    parse_mode: Literal["HTML"] = "HTML"


@dataclass(frozen=True, slots=True)
class DigestEntry:
    """One line of a digest."""

    sender: str
    subject: str


def _safe(value: str, cap: int) -> str:
    """Cap first, then escape, so a cut never lands inside an entity. Line breaks become spaces."""
    return html.escape(" ".join(value[:cap].split()), quote=False)


def _address(value: str) -> str:
    return parseaddr(value)[1].casefold()


def _warnings(meta: MailMeta, auth: AuthResults) -> list[str]:
    lines: list[str] = []
    if meta.reply_to and _address(meta.reply_to) != _address(meta.sender):
        lines.append(
            f"⚠️ Reply-To differs from the sender: replies would go to {_safe(meta.reply_to, SENDER_CHARS)}. "
            f"I reply to {_safe(_address(meta.sender) or meta.sender, SENDER_CHARS)} unless you say otherwise."
        )
    if any(result in _FAILED for result in (auth.spf, auth.dkim, auth.dmarc)):
        lines.append("⚠️ The sender could not be verified (SPF, DKIM or DMARC failed). Be careful.")
    if meta.has_attachment:
        lines.append("📎 This mail has an attachment (not opened).")
    return lines


def _alert_text(meta: MailMeta, judgement: Judgement, auth: AuthResults, scale: float) -> str:
    def cap(chars: int) -> int:
        return max(10, int(chars * scale))

    lines = [
        f"<b>From:</b> {_safe(meta.sender, cap(SENDER_CHARS))}",
        f"<b>Subject:</b> {_safe(meta.subject, cap(SUBJECT_CHARS))}",
        f"<b>Why it matters:</b> {_safe(judgement.reason, cap(REASON_CHARS))}",
        f"<b>Summary:</b> {_safe(judgement.summary, cap(SUMMARY_CHARS))}",
        *_warnings(meta, auth),
    ]
    return "\n".join(lines)


def build_alert(alert_id: str, meta: MailMeta, judgement: Judgement, auth: AuthResults) -> AlertMessage:
    """One alert: facts, warnings and exactly three buttons. Shrinks the long fields until the message fits."""
    scale = 1.0
    text = _alert_text(meta, judgement, auth, scale)
    while len(text) > MAX_MESSAGE_CHARS and scale > 0.05:  # noqa: PLR2004 - give up shrinking at a tiny size
        scale /= 2
        text = _alert_text(meta, judgement, auth, scale)
    buttons = (
        Button("Reply", f"reply:{alert_id}"[:BUTTON_DATA_MAX]),
        Button("Remind me later", f"later:{alert_id}"[:BUTTON_DATA_MAX]),
        Button("No more reminders", f"stop:{alert_id}"[:BUTTON_DATA_MAX]),
    )
    return AlertMessage(text=text[:MAX_MESSAGE_CHARS], buttons=buttons)


def build_digest(entries: Sequence[DigestEntry], *, held: bool) -> AlertMessage:
    """One summary message for several alerts (hourly cap, or held during quiet hours); no buttons."""
    title = (
        f"<b>{len(entries)} urgent mails while you were away</b>"
        if held
        else f"<b>{len(entries)} more urgent mails</b> (too many alerts this hour, so I batched them)"
    )
    lines = [
        f"• {_safe(entry.sender, DIGEST_SENDER_CHARS)}: {_safe(entry.subject, DIGEST_SUBJECT_CHARS)}"
        for entry in entries[:DIGEST_LISTED]
    ]
    while lines and len(_digest_text(title, lines, len(entries))) > MAX_MESSAGE_CHARS:
        lines.pop()
    return AlertMessage(text=_digest_text(title, lines, len(entries))[:MAX_MESSAGE_CHARS], buttons=())


def _digest_text(title: str, lines: list[str], total: int) -> str:
    more = total - len(lines)
    tail = [f"…and {more} more"] if more > 0 else []
    return "\n".join([title, *lines, *tail])
