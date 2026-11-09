"""The daily overview: counts per category and the mails the agent was unsure about (spec AC-31).

The times come from the ``TimePolicy`` handed in (the default one until the settings arrive, INT-002). A local date is
settled when its overview time has passed and quiet hours are over: either one message goes out or, when nothing was
filed, none. Either way the date is remembered, so a late mail never triggers a second look. The mail of an overview
is everything filed since the previous one was settled (AC-27).
"""

from __future__ import annotations

import html
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.core.alert_text import MAX_MESSAGE_CHARS, AlertMessage
from app.core.judgement import LOW_CONFIDENCE
from app.core.time_policy import day_start, in_quiet_hours, local_day, overview_on

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date, datetime

    from app.usecases.policy_notice import PolicySource

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


class FiledMails(Protocol):
    """The mails the overview counts."""

    async def filed_without_alert_since(self, since: datetime) -> list[FiledMail]:
        """Mails filed since ``since`` that did not raise an alert."""
        ...


class OverviewLog(Protocol):
    """Which local dates were settled, and the instant each was settled."""

    async def overview_sent(self, day: date) -> bool:
        """Whether the overview for this local date was settled."""
        ...

    async def mark_overview_sent(self, day: date, settled_at: datetime) -> None:
        """Remember that the overview for this local date was settled at ``settled_at``."""
        ...

    async def last_settled_at(self) -> datetime | None:
        """The latest settled instant, or None when no overview was ever settled."""
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

    def __init__(
        self, mails: FiledMails, log: OverviewLog, outbox: Outbox, now: Callable[[], datetime], policies: PolicySource
    ) -> None:
        """Wire the mail store, the overview log, the Telegram outbox, the clock and the source of the times."""
        self._mails = mails
        self._log = log
        self._outbox = outbox
        self._now = now
        self._policies = policies

    async def send_overview(self) -> None:
        """Send the overview once per local date, once its time has passed and outside quiet hours.

        The window of mail runs from the instant the previous overview was settled, so a change of zone can neither
        skip nor repeat a mail. Without a previous overview it starts at the beginning of the local day.
        """
        policy = await self._policies.current()  # one snapshot for the whole run
        now = self._now()
        today = local_day(now, policy)
        if now < overview_on(today, policy) or in_quiet_hours(now, policy) or await self._log.overview_sent(today):
            return
        since = await self._log.last_settled_at() or day_start(today, policy)
        mails = await self._mails.filed_without_alert_since(since)
        if mails:
            await self._outbox.send(build_overview(mails))
        await self._log.mark_overview_sent(today, now)
