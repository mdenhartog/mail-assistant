"""The daily overview: counts per category and the mails the agent was unsure about (spec AC-31).

The time comes from ``time_policy`` (a constant for the first release, INT-002 may make it adjustable). A day is
settled when its overview time has passed and quiet hours are over: either one message goes out or, when nothing was
filed, none. Either way the day is remembered, so a late mail never triggers a second look.
"""

from __future__ import annotations

import html
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from app.core import time_policy
from app.core.alert_text import MAX_MESSAGE_CHARS, AlertMessage
from app.core.judgement import LOW_CONFIDENCE

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

LABEL_PREFIX = "Assistant/"
UNSURE_LISTED = 10
SENDER_CHARS = 60
SUBJECT_CHARS = 80


@dataclass(frozen=True, slots=True)
class FiledMail:
    """A mail filed without an alert, as far as the overview needs to know it."""

    label: str
    confidence: float
    sender: str
    subject: str
    urgent: bool = False  # judged urgent but no alert was sent (the one-time catch-up caps its alerts, INT-003)


class OverviewStore(Protocol):
    """Persistence for the overview."""

    async def filed_without_alert_since(self, since: datetime) -> list[FiledMail]:
        """Mails filed since ``since`` that did not raise an alert."""
        ...

    async def overview_sent(self, day: date) -> bool:
        """Whether the overview for this day was settled."""
        ...

    async def mark_overview_sent(self, day: date) -> None:
        """Remember that the overview for this day was settled."""
        ...


class Outbox(Protocol):
    """Telegram, sending to the owner's chat."""

    async def send(self, message: AlertMessage) -> int:
        """Send and return the Telegram message id."""
        ...


def _safe(value: str, cap: int) -> str:
    return html.escape(" ".join(value[:cap].split()), quote=False)


def _name(label: str) -> str:
    return label.removeprefix(LABEL_PREFIX)


def _line(mail: FiledMail, *, with_label: bool) -> str:
    who, what = _safe(mail.sender, SENDER_CHARS), _safe(mail.subject, SUBJECT_CHARS)
    return f"• {who}: {what} ({_safe(_name(mail.label), 40)})" if with_label else f"• {who}: {what}"


def _text(mails: list[FiledMail], listed: int) -> str:
    counts = Counter(_name(mail.label) for mail in mails).most_common()
    lines = [f"<b>Today I filed {len(mails)} mails</b>", *(f"• {_safe(name, 40)}: {count}" for name, count in counts)]
    unsure = [mail for mail in mails if mail.confidence < LOW_CONFIDENCE]
    if unsure:
        lines.append(f"\n<b>I was unsure about {len(unsure)}:</b>")
        lines.extend(_line(mail, with_label=True) for mail in unsure[:listed])
        if len(unsure) > listed:
            lines.append(f"…and {len(unsure) - listed} more")
    urgent = [mail for mail in mails if mail.urgent]
    if urgent:
        lines.append(f"\n<b>Old mail that looked urgent ({len(urgent)}):</b>")
        lines.extend(_line(mail, with_label=False) for mail in urgent[:listed])
        if len(urgent) > listed:
            lines.append(f"…and {len(urgent) - listed} more")
    return "\n".join(lines)


def build_overview(mails: list[FiledMail]) -> AlertMessage:
    """One message without buttons; shortens the unsure list until it fits."""
    listed = UNSURE_LISTED
    text = _text(mails, listed)
    while len(text) > MAX_MESSAGE_CHARS and listed > 0:
        listed -= 1
        text = _text(mails, listed)
    return AlertMessage(text=text[:MAX_MESSAGE_CHARS], buttons=())


class OverviewService:
    """Sends the overview when it is due."""

    def __init__(self, store: OverviewStore, outbox: Outbox, now: Callable[[], datetime]) -> None:
        """Wire the store, the Telegram outbox and the clock."""
        self._store = store
        self._outbox = outbox
        self._now = now

    async def send_overview(self) -> None:
        """Send the overview for the latest overview time that has passed, once, outside quiet hours."""
        now = self._now()
        if time_policy.in_quiet_hours(now):
            return
        due = self._pending_due(now)
        if due is None or await self._store.overview_sent(due.date()):
            return
        start = datetime.combine(due.date(), datetime.min.time(), tzinfo=time_policy.TIME_ZONE)
        mails = await self._store.filed_without_alert_since(start)
        if mails:
            await self._outbox.send(build_overview(mails))
        await self._store.mark_overview_sent(due.date())

    @staticmethod
    def _pending_due(now: datetime) -> datetime | None:
        """Today's overview time once it has passed; yesterday's only when quiet hours pushed it back."""
        local = now.astimezone(time_policy.TIME_ZONE)
        today = datetime.combine(local.date(), time_policy.OVERVIEW_AT, tzinfo=time_policy.TIME_ZONE)
        if local >= today:
            return today
        yesterday = today - timedelta(days=1)
        return yesterday if time_policy.in_quiet_hours(yesterday) else None
