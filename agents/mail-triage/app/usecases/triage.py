"""The triage pipeline: list new mail, judge it, file it, open an alert state (spec AC-1 to 4, AC-12, AC-26, AC-27).

The pipeline only knows ports (``Mailbox``, ``Judge``, ``TriageStore``, ``FailureNotifier``), so it is tested with fakes
and wired to Gmail, Anthropic and PostgreSQL elsewhere. The mailbox port has no way to delete anything. The history
position moves forward only when every listed mail is settled, so a crash or an outage never loses a mail, and the
claim in the store keeps a mail from being judged twice.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from app.adapters.gmail_read import HistoryExpiredError
from app.adapters.judge_anthropic import ModelUnavailable, trim_mail
from app.core.alert_state import AlertState, initial_state
from app.core.alert_text import AuthResults
from app.core.auth_results import parse_auth_results
from app.core.judgement import (
    OTHER_ID,
    OTHER_LABEL,
    Filing,
    Judgement,
    JudgingList,
    NeedsAttention,
    category_label,
    resolve,
)
from app.core.pinned import PinnedKind, PinnedSenders, pinned_kind
from app.core.sender_rules import FilingSource, RuleFiling, RuleSkipped, SenderRulesCache
from app.core.time_policy import in_quiet_hours, next_quiet_end

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail
    from app.adapters.judge_anthropic import TrimmedMail
    from app.core.judgement import ListedCategory
    from app.core.sender_rules import UrgencyJudge, UrgencyVerdict
    from app.usecases.policy_notice import PolicySource
    from schedule_policy.policy import TimePolicy

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
class FilingEntry:
    """The ``filing`` row of a labelled mail: its topic, extra label, source and the list version used.

    ``source_ref`` is the matched sender entry, never anything of the mail itself. No sender, no subject (AC-39).
    """

    category_id: str  # the topic
    list_version: int
    extra_id: str | None = None
    source: FilingSource = FilingSource.MODEL
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class Outcome:
    """What became of one mail: its label, urgency, alert state and content.

    ``label`` and ``filing`` are ``None`` for pinned mail, which stays in the inbox (AC-39), and ``filing`` is also
    ``None`` while no list version exists.
    """

    label: str | None
    urgent: bool
    confidence: float | None
    alert: AlertState | None
    note: str
    content: MailContent
    release_at: datetime | None = None  # a held alert: the next quiet end under the policy valid when it was held
    filing: FilingEntry | None = None
    extra_label: str | None = None  # a sender rule's extra label, added next to ``label``


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

    def add_label(self, message_id: str, label_id: str) -> None:
        """Add one more label (the extra label) and change nothing else."""
        ...


class Judge(Protocol):
    """The model adapter."""

    async def judge(self, mail: TrimmedMail, categories: Sequence[ListedCategory]) -> Judgement | NeedsAttention:
        """A valid judgement for this one mail against ``categories``, or needs-attention."""
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

    async def current_list(self) -> JudgingList:
        """The latest list version with its categories (version 0 and none before the first version is written)."""
        ...

    async def complete(self, message_id: str, outcome: Outcome) -> None:
        """Record the outcome for a mail: its alert state when it needs one, its ``filing`` row when labelled."""
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


def _content(mail: FetchedMail, reason: str, summary: str) -> MailContent:
    return MailContent(
        sender=mail.sender,
        subject=mail.subject,
        reply_to=mail.reply_to,
        has_attachment=mail.has_attachment,
        reason=reason,
        summary=summary,
        auth=parse_auth_results(mail.auth_results[0] if mail.auth_results else None),
    )


def pinned_mail_kind(mail: FetchedMail, senders: PinnedSenders) -> PinnedKind | None:
    """The pinned kind of the app's own sign-in mail and Google security mail, by Gmail's verdict only (AC-39)."""
    return pinned_kind(mail.auth_results, mail.sender, senders)


def pinned_outcome(kind: PinnedKind, mail: FetchedMail, now: datetime, policy: TimePolicy) -> Outcome:
    """Pinned mail stays in the inbox: no label, no filing, no model call (AC-39, ADR-0048).

    Google security mail raises an urgent alert, held in quiet hours like any other, and keeps its capped content for
    the alert text. Sign-in code mail raises no alert and keeps no sender or subject: its text never reaches Telegram.
    """
    if kind is PinnedKind.SIGN_IN_CODE:
        content = MailContent(
            "", "", None, has_attachment=False, reason="", summary="", auth=AuthResults(None, None, None)
        )
        return Outcome(None, urgent=False, confidence=None, alert=None, note=f"pinned:{kind.value}", content=content)
    alert = initial_state(in_quiet_hours=in_quiet_hours(now, policy))
    return Outcome(
        None,
        urgent=True,
        confidence=None,
        alert=alert,
        note=f"pinned:{kind.value}",
        content=_content(mail, "Google security mail", ""),
        release_at=next_quiet_end(now, policy) if alert is AlertState.HELD else None,
    )


def decide_outcome(
    verdict: Judgement | NeedsAttention,
    mail: FetchedMail,
    current: JudgingList,
    now: datetime,
    policy: TimePolicy,
) -> Outcome:
    """Label, urgency, filing and content of one judged mail. Anything untrustworthy is urgent, never ignorable.

    Shared by the pipeline (new mail) and the catch-up (old mail), so both decide exactly alike. ``policy`` is the
    snapshot of this one decision: inside its quiet hours the alert is held until the next quiet end under it.
    ``current`` is the list snapshot the mail was judged against; its version goes into the filing.
    """
    decision = resolve(verdict, current.categories) if isinstance(verdict, Judgement) else verdict
    category_id = OTHER_ID
    if isinstance(decision, Filing):
        label, category_id, urgent, confidence, note = (
            decision.label,
            decision.category_id,
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
    content = _content(mail, reason, summary)
    alert = initial_state(in_quiet_hours=in_quiet_hours(now, policy)) if urgent else None
    release_at = next_quiet_end(now, policy) if alert is AlertState.HELD else None
    return Outcome(
        label=label,
        urgent=urgent,
        confidence=confidence,
        alert=alert,
        note=note,
        content=content,
        release_at=release_at,
        filing=FilingEntry(category_id, current.version) if current.version > 0 else None,
    )


def rule_outcome(  # noqa: PLR0913, PLR0917 - the snapshot of one decision
    ruled: RuleFiling,
    verdict: UrgencyVerdict | None,
    mail: FetchedMail,
    current: JudgingList,
    now: datetime,
    policy: TimePolicy,
) -> Outcome:
    """Label, filing and urgency of a mail a sender rule filed (D11): ``verdict`` is ``None`` in a ticked category."""
    urgent = verdict is not None and verdict.needs_attention
    reason = f"Needs attention: {verdict.reason}" if urgent and verdict else f"Sender rule: {ruled.entry}"
    alert = initial_state(in_quiet_hours=in_quiet_hours(now, policy)) if urgent else None
    extra = ruled.extra
    return Outcome(
        label=category_label(ruled.topic),
        urgent=urgent,
        confidence=1.0,
        alert=alert,
        note="sender_rule",
        content=_content(mail, reason, ""),
        release_at=next_quiet_end(now, policy) if alert is AlertState.HELD else None,
        filing=FilingEntry(
            ruled.topic.category_id,
            current.version,
            extra.category_id if extra else None,
            FilingSource.SENDER_RULE,
            ruled.entry,
        ),
        extra_label=category_label(extra) if extra else None,
    )


def mark_not_applied(outcome: Outcome, skipped: RuleSkipped | None) -> Outcome:
    """Record on the filing that a listed sender was not authenticated, so its rule was not applied (D16)."""
    if skipped is None or outcome.filing is None:
        return outcome
    filing = replace(outcome.filing, source=FilingSource.SENDER_RULE_NOT_APPLIED, source_ref=skipped.entry)
    return replace(outcome, filing=filing)


class TriagePipeline:
    """One run of the poll loop."""

    def __init__(  # noqa: PLR0913, PLR0917 - every part is injected for tests
        self,
        mailbox: Mailbox,
        judge: Judge,
        store: TriageStore,
        notifier: FailureNotifier,
        now: Callable[[], datetime],
        policy: PolicySource,
        pinned: PinnedSenders,
        urgency: UrgencyJudge,
    ) -> None:
        """Wire the ports, the clock, the policy source, the pinned sender domains and the urgency-only judge."""
        self._urgency = urgency
        self._rules = SenderRulesCache()
        self._pinned = pinned
        self._mail = mailbox
        self._judge = judge
        self._store = store
        self._notifier = notifier
        self._now = now
        self._policy = policy

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
        kind = pinned_mail_kind(mail, self._pinned)  # checked again here, right before anything could move it
        if kind is not None:
            policy = await self._policy.current()  # one snapshot for this mail
            outcome = pinned_outcome(kind, mail, self._now(), policy)
            await self._store.complete(mail.message_id, outcome)
            summary.alerts += outcome.alert is not None
            return
        current = await self._store.current_list()  # one snapshot for this mail: the judgement and the filing agree
        ruled = self._rules.for_list(current).apply(mail.auth_results, mail.sender)
        outcome = await self._decide(mail, current, ruled)
        await self._file(mail, outcome)
        summary.filed += 1
        summary.alerts += outcome.alert is not None

    async def _decide(self, mail: FetchedMail, current: JudgingList, ruled: RuleFiling | RuleSkipped | None) -> Outcome:
        """A sender rule files the mail without a category call; otherwise the model judges it."""
        trimmed = trim_mail(mail.subject, mail.sender, mail.text)
        if isinstance(ruled, RuleFiling):
            verdict = None if ruled.ticked else await self._urgency.needs_attention(trimmed)
            policy = await self._policy.current()
            return rule_outcome(ruled, verdict, mail, current, self._now(), policy)
        judged = await self._judge.judge(trimmed, current.categories)
        policy = await self._policy.current()  # one snapshot for this mail: the decision never mixes old and new values
        return mark_not_applied(decide_outcome(judged, mail, current, self._now(), policy), ruled)

    async def _file(self, mail: FetchedMail, outcome: Outcome) -> None:
        outcome, label_id = await self._topic_label(mail, outcome)
        outcome = await self._add_extra(mail, outcome)
        await asyncio.to_thread(self._mail.file, mail.message_id, label_id)
        await self._store.complete(mail.message_id, outcome)

    async def _topic_label(self, mail: FetchedMail, outcome: Outcome) -> tuple[Outcome, str]:
        try:
            return outcome, await asyncio.to_thread(self._mail.ensure_label, outcome.label or OTHER_LABEL)
        except ValueError:  # the mailbox refuses this label name: file under Other, never lose the mail or its alert
            logger.warning("label refused; filing under Other id=%s", mail.message_id)
            return replace(outcome, label=OTHER_LABEL), await asyncio.to_thread(self._mail.ensure_label, OTHER_LABEL)

    async def _add_extra(self, mail: FetchedMail, outcome: Outcome) -> Outcome:
        """Add the extra label before the mail leaves the inbox; a refused name drops the extra, never the mail."""
        if outcome.extra_label is None or outcome.filing is None:
            return outcome
        try:
            label_id = await asyncio.to_thread(self._mail.ensure_label, outcome.extra_label)
        except ValueError:
            logger.warning("extra label refused id=%s", mail.message_id)
            return replace(outcome, extra_label=None, filing=replace(outcome.filing, extra_id=None))
        await asyncio.to_thread(self._mail.add_label, mail.message_id, label_id)
        return outcome
