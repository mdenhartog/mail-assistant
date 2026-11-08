"""The triage pipeline: list new mail, judge it, file it, open an alert state (spec AC-1 to 4, AC-12, AC-26, AC-27).

The pipeline only knows ports (``Mailbox``, ``Judge``, ``TriageStore``, ``FailureNotifier``), so it is tested with fakes
and wired to Gmail, Anthropic and PostgreSQL elsewhere. The mailbox port has no way to delete anything. The history
position moves forward only when every listed mail is settled, so a crash or an outage never loses a mail, and the
claim in the store keeps a mail from being judged twice.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from app.adapters.gmail_read import HistoryExpiredError
from app.adapters.judge_anthropic import ModelUnavailable, trim_mail
from app.core.alert_state import AlertState, initial_state
from app.core.auth_results import parse_auth_results
from app.core.judgement import OTHER_LABEL, Filing, Judgement, NeedsAttention, resolve
from app.core.time_policy import in_quiet_hours

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail
    from app.adapters.judge_anthropic import TrimmedMail
    from app.core.alert_text import AuthResults

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # tries per mail before it is given up on and one notice is requested


@dataclass(frozen=True, slots=True)
class MailContent:
    """The capped, mail-derived content kept for alerts and the overview (ADR-0020). Never the body."""

    sender: str
    subject: str
    reply_to: str | None
    has_attachment: bool
    reason: str
    summary: str
    auth: AuthResults


@dataclass(frozen=True, slots=True)
class Outcome:
    """What became of one mail: its label, urgency, alert state and content."""

    label: str
    urgent: bool
    confidence: float | None
    alert: AlertState | None
    note: str
    content: MailContent


class Claim(StrEnum):
    """What the store says about a mail when the pipeline claims it."""

    NEW = "new"
    PENDING = "pending"  # claimed earlier, never completed (a crash): process it again
    DONE = "done"


class Mailbox(Protocol):
    """Gmail as the pipeline needs it. Blocking calls; the pipeline runs them in a thread."""

    def list_new(self, history_id: str | None) -> tuple[list[str], str]:
        """New inbox mail ids since ``history_id`` and the new position."""
        ...

    def fetch(self, message_id: str) -> FetchedMail:
        """Headers and text of one mail."""
        ...

    def ensure_label(self, name: str) -> str:
        """Id of the label, created when missing."""
        ...

    def file(self, message_id: str, label_id: str) -> None:
        """Add the category label and remove the inbox label."""
        ...


class Judge(Protocol):
    """The model adapter."""

    async def judge(self, mail: TrimmedMail) -> Judgement | NeedsAttention:
        """A valid judgement, or needs-attention."""
        ...


class TriageStore(Protocol):
    """Persistence as the pipeline needs it."""

    async def history_id(self) -> str | None:
        """The stored Gmail history position."""
        ...

    async def save_history_id(self, value: str) -> None:
        """Store the new position."""
        ...

    async def claim(self, message_id: str, thread_id: str) -> Claim:
        """Claim a mail: ``NEW`` for the first caller only."""
        ...

    async def known_labels(self) -> list[str]:
        """Category labels in use."""
        ...

    async def complete(self, message_id: str, outcome: Outcome) -> None:
        """Record the outcome for a mail, with its alert state when it needs one."""
        ...

    async def record_failure(self, message_id: str) -> int:
        """Count one more failed attempt and return the total."""
        ...

    async def abandon(self, message_id: str) -> None:
        """Stop retrying this mail."""
        ...


class FailureNotifier(Protocol):
    """Asks for one error notice to Marco."""

    async def notify_failure(self, message_id: str) -> None:
        """Request the notice for a mail that was given up on."""
        ...


@dataclass(slots=True)
class RunSummary:
    """What one run did; counts only, never mail content."""

    filed: int = 0
    alerts: int = 0
    retry_later: int = 0
    given_up: int = 0
    model_down: bool = False
    listing_failed: bool = False


class TriagePipeline:
    """One run of the poll loop."""

    def __init__(
        self,
        mailbox: Mailbox,
        judge: Judge,
        store: TriageStore,
        notifier: FailureNotifier,
        now: Callable[[], datetime],
    ) -> None:
        """Wire the ports and the clock."""
        self._mail = mailbox
        self._judge = judge
        self._store = store
        self._notifier = notifier
        self._now = now

    async def run_once(self) -> RunSummary:
        """Process every new mail once; move the position forward only when nothing is left to retry."""
        summary = RunSummary()
        position = await self._store.history_id()
        listed = await self._list(position, summary)
        if listed is None:
            return summary
        ids, new_position = listed
        for message_id in ids:
            if not await self._process(message_id, summary):
                return summary
        if summary.retry_later == 0:
            await self._store.save_history_id(new_position)
        return summary

    async def _list(self, position: str | None, summary: RunSummary) -> tuple[list[str], str] | None:
        try:
            try:
                return await asyncio.to_thread(self._mail.list_new, position)
            except HistoryExpiredError:
                logger.warning("gmail history position expired; starting again from now")
                return await asyncio.to_thread(self._mail.list_new, None)
        except Exception as error:
            logger.warning("listing new mail failed kind=%s", type(error).__name__)
            summary.listing_failed = True
            return None

    async def _process(self, message_id: str, summary: RunSummary) -> bool:
        """Handle one mail. ``False`` means the model is down and the run should stop."""
        try:
            await self._triage(message_id, summary)
        except ModelUnavailable:
            logger.warning("model unavailable; leaving the remaining mail for the next run")
            summary.model_down = True
            summary.retry_later += 1
            return False
        except Exception as error:
            logger.warning("processing failed id=%s kind=%s", message_id, type(error).__name__)
            await self._fail(message_id, summary)
        return True

    async def _fail(self, message_id: str, summary: RunSummary) -> None:
        attempts = await self._store.record_failure(message_id)
        if attempts < MAX_ATTEMPTS:
            summary.retry_later += 1
            return
        if attempts == MAX_ATTEMPTS:  # the one notice
            await self._store.abandon(message_id)
            await self._notifier.notify_failure(message_id)
            summary.given_up += 1

    async def _triage(self, message_id: str, summary: RunSummary) -> None:
        mail = await asyncio.to_thread(self._mail.fetch, message_id)
        if await self._store.claim(mail.message_id, mail.thread_id) is Claim.DONE:
            return
        verdict = await self._judge.judge(trim_mail(mail.subject, mail.sender, mail.text))
        outcome = await self._decide(verdict, mail)
        label_id = await asyncio.to_thread(self._mail.ensure_label, outcome.label)
        await asyncio.to_thread(self._mail.file, mail.message_id, label_id)
        await self._store.complete(mail.message_id, outcome)
        summary.filed += 1
        summary.alerts += outcome.alert is not None

    async def _decide(self, verdict: Judgement | NeedsAttention, mail: FetchedMail) -> Outcome:
        """Label, urgency and content. Anything untrustworthy is urgent, never ignorable."""
        decision = resolve(verdict, await self._store.known_labels()) if isinstance(verdict, Judgement) else verdict
        if isinstance(decision, Filing):
            label, urgent, confidence, note = (
                decision.label,
                decision.judgement.urgent,
                decision.judgement.confidence,
                "",
            )
        else:
            label, urgent, confidence, note = OTHER_LABEL, True, None, f"needs_attention:{decision.reason}"
        if isinstance(verdict, Judgement):
            reason, summary = verdict.reason, verdict.summary
        else:
            reason, summary = f"Needs attention: {verdict.reason}", ""
        content = MailContent(
            sender=mail.sender,
            subject=mail.subject,
            reply_to=mail.reply_to,
            has_attachment=mail.has_attachment,
            reason=reason,
            summary=summary,
            auth=parse_auth_results(mail.headers.get("Authentication-Results")),
        )
        alert = initial_state(in_quiet_hours=in_quiet_hours(self._now())) if urgent else None
        return Outcome(label=label, urgent=urgent, confidence=confidence, alert=alert, note=note, content=content)
