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

from app.adapters.gmail_read import HistoryExpiredError, LabelRefused
from app.adapters.judge_anthropic import ModelUnavailable, trim_mail
from app.core.alert_decision import AlertCause, decide_alert
from app.core.alert_state import AlertState, initial_state
from app.core.authentication import authenticated_from_domain
from app.core.judgement import (
    OTHER_ID,
    Filing,
    Judgement,
    JudgingList,
    NeedsAttention,
    category_label,
    resolve,
)
from app.core.managed import LabelRef
from app.core.pinned import PinnedKind, PinnedSenders, pinned_kind
from app.core.scope import Scope, classify
from app.core.sender_rules import (
    ExtraRule,
    FilingSource,
    RuleFiling,
    RuleSkipped,
    SenderRulesCache,
    UrgencyNotJudged,
    UrgencyVerdict,
)
from app.core.time_policy import in_quiet_hours, next_quiet_end

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail
    from app.adapters.judge_anthropic import TrimmedMail
    from app.core.judgement import ListedCategory
    from app.core.managed import ManagedLabel, ManagedSet
    from app.core.sender_rules import UrgencyJudge
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
    verified_domain: str | None  # the From domain Gmail vouches for; ``None`` when it does not (ADR-0054)


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
    causes: tuple[AlertCause, ...] = ()  # why the alert exists; empty when there is none (ADR-0057)


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

    def ensure_label(self, label: ManagedLabel) -> str:
        """Id of the managed label, created when missing."""
        ...

    def file(self, message_id: str, label_id: str) -> str:
        """Add the managed label and remove the inbox label; the id used comes back (new when it was recreated)."""
        ...

    def add_label(self, message_id: str, label_id: str) -> str:
        """Add one more managed label (the extra label) and change nothing else; the id used comes back."""
        ...


class LabelBook(Protocol):
    """The managed labels and the label settings, as the settings and the stored label ids know them (ADR-0060)."""

    async def managed(self) -> ManagedSet:
        """The managed labels of this moment: the list's categories, "Other" and the archive label."""
        ...

    async def names(self) -> dict[str, str]:
        """Gmail label id to its current name, for the labels a mail carries."""
        ...

    async def other(self) -> ManagedLabel:
        """The "Other" setting: its name and, once known, its Gmail id."""
        ...

    async def topic(self, category_id: str) -> ManagedLabel:
        """The list label of one category of the current list (a topic or an extra label)."""
        ...

    async def remember(self, label: ManagedLabel, label_id: str) -> None:
        """Store the Gmail id of a managed label when it is not the id stored before."""
        ...


class Judge(Protocol):
    """The model adapter."""

    async def judge(
        self, mail: TrimmedMail, categories: Sequence[ListedCategory], instructions: str
    ) -> Judgement | NeedsAttention:
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


async def mail_scope(mail: FetchedMail, book: LabelBook) -> Scope:
    """What the managed set says about the labels one mail carries; ids decide, names only while no id is known."""
    names = await book.names()
    refs = [LabelRef(label_id, names.get(label_id, "")) for label_id in mail.labels]
    return classify(refs, await book.managed())


async def label_of(outcome: Outcome, book: LabelBook) -> ManagedLabel:
    """The managed label an outcome is filed under: its category's list label, else the "Other" setting."""
    filing = outcome.filing
    if filing is None or filing.category_id == OTHER_ID:
        return await book.other()
    return await book.topic(filing.category_id)


class _Filer(Protocol):
    def ensure_label(self, label: ManagedLabel) -> str: ...

    def file(self, message_id: str, label_id: str) -> str: ...


async def ensure_id(mailbox: _Filer, book: LabelBook, label: ManagedLabel) -> str:
    """The Gmail id of a managed label (created when missing); stored when it is not the id stored before."""
    label_id = await asyncio.to_thread(mailbox.ensure_label, label)
    if label_id != label.label_id:
        await book.remember(label, label_id)
    return label_id


async def file_under_label(mailbox: _Filer, book: LabelBook, message_id: str, label: ManagedLabel) -> None:
    """Add the managed label to the mail by id and take it out of the inbox; store a changed id."""
    label_id = await ensure_id(mailbox, book, label)
    await file_ensured(mailbox, book, message_id, label, label_id)


async def file_ensured(mailbox: _Filer, book: LabelBook, message_id: str, label: ManagedLabel, label_id: str) -> None:
    """File a mail under the managed label with its ensured id; store the id when Gmail used another."""
    used = await asyncio.to_thread(mailbox.file, message_id, label_id)
    if used != label_id:
        await book.remember(label, used)


def _verified_domain(mail: FetchedMail) -> str | None:
    """The From domain when Gmail vouches for it (the one verdict on the sender), else ``None``."""
    headers = tuple(("Authentication-Results", value) for value in mail.auth_results)
    return authenticated_from_domain(headers, mail.sender)


def _content(mail: FetchedMail, reason: str, summary: str) -> MailContent:
    return MailContent(
        sender=mail.sender,
        subject=mail.subject,
        reply_to=mail.reply_to,
        has_attachment=mail.has_attachment,
        reason=reason,
        summary=summary,
        verified_domain=_verified_domain(mail),
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
        content = MailContent("", "", None, has_attachment=False, reason="", summary="", verified_domain=None)
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
        causes=_urgent_causes(urgent=True),
    )


def decide_outcome(  # noqa: PLR0913 - the snapshot of one decision, as rule_outcome
    verdict: Judgement | NeedsAttention,
    mail: FetchedMail,
    current: JudgingList,
    now: datetime,
    policy: TimePolicy,
    *,
    other_label: str,
) -> Outcome:
    """Label, urgency, filing and content of one judged mail. Anything untrustworthy is urgent, never ignorable.

    Shared by the pipeline (new mail) and the catch-up (old mail), so both decide exactly alike. ``policy`` is the
    snapshot of this one decision: inside its quiet hours the alert is held until the next quiet end under it.
    ``current`` is the list snapshot the mail was judged against; its version goes into the filing.
    ``other_label`` is the name of the "Other" setting, where a mail with no fitting category goes.
    """
    decision = (
        resolve(verdict, current.categories, other_label=other_label) if isinstance(verdict, Judgement) else verdict
    )
    category_id, extra = OTHER_ID, None
    if isinstance(decision, Filing):
        extra = decision.extra
        label, category_id, urgent, confidence, note = (
            decision.label,
            decision.category_id,
            decision.judgement.urgent,
            decision.judgement.confidence,
            "",
        )
    else:
        label, urgent, confidence, note = other_label, True, None, f"needs_attention:{decision.reason}"
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
        filing=FilingEntry(category_id, current.version, extra.category_id if extra else None)
        if current.version > 0
        else None,
        extra_label=category_label(extra) if extra else None,
        causes=_urgent_causes(urgent=urgent),
    )


def rule_outcome(  # noqa: PLR0913, PLR0917 - the snapshot of one decision
    ruled: RuleFiling,
    verdict: UrgencyVerdict | UrgencyNotJudged | None,
    mail: FetchedMail,
    current: JudgingList,
    now: datetime,
    policy: TimePolicy,
) -> Outcome:
    """Label, filing and urgency of a mail a sender rule filed (D11).

    ``verdict`` is ``None`` in a ticked category and ``UrgencyNotJudged`` when the budget above the reserve was used
    up: the mail is then filed, not urgent, and left for the daily overview (C-18).
    """
    judged = verdict if isinstance(verdict, UrgencyVerdict) else None
    urgent = judged is not None and judged.needs_attention
    reason = f"Needs attention: {judged.reason}" if urgent and judged else f"Sender rule: {ruled.entry}"
    note = "sender_rule"
    if isinstance(verdict, UrgencyNotJudged):
        reason, note = (
            f"Sender rule: {ruled.entry}; urgency not judged ({verdict.reason})",
            "sender_rule:urgency_not_judged",
        )
    alert = initial_state(in_quiet_hours=in_quiet_hours(now, policy)) if urgent else None
    extra = ruled.extra
    return Outcome(
        label=category_label(ruled.topic),
        urgent=urgent,
        confidence=1.0,
        alert=alert,
        note=note,
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
        causes=_urgent_causes(urgent=urgent),
    )


def _urgent_causes(*, urgent: bool) -> tuple[AlertCause, ...]:
    decision = decide_alert(urgent=urgent, ticked=())
    return decision.causes if decision else ()


def with_always_notify(outcome: Outcome, current: JudgingList, now: datetime, policy: TimePolicy) -> Outcome:
    """Add the always-notify causes of a NEW mail: its topic and extra label are ticked in the list it was filed by.

    One decision for the mail: an urgent alert gets the tick causes added, a non-urgent one is created (held inside
    quiet hours, like any other). Only the pipeline calls this; the catch-up and the re-sort never do (ADR-0057).
    """
    filing = outcome.filing
    if filing is None:
        return outcome
    filed_under = {filing.category_id, filing.extra_id}
    ticked = [
        category.name for category in current.categories if category.notify and category.category_id in filed_under
    ]
    decision = decide_alert(urgent=outcome.urgent, ticked=ticked)
    if decision is None:
        return outcome
    if outcome.alert is not None:
        return replace(outcome, causes=decision.causes)
    alert = initial_state(in_quiet_hours=in_quiet_hours(now, policy))
    release_at = next_quiet_end(now, policy) if alert is AlertState.HELD else None
    return replace(outcome, causes=decision.causes, alert=alert, release_at=release_at)


def with_rule_extra(outcome: Outcome, rule: ExtraRule) -> Outcome:
    """Add the extra label a sender rule lists next to the model's topic; the rule's label replaces the model's."""
    if outcome.filing is None:
        return outcome
    return replace(
        outcome,
        extra_label=category_label(rule.extra),
        filing=replace(outcome.filing, extra_id=rule.extra.category_id),
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
        labels: LabelBook,
    ) -> None:
        """Wire the ports, the clock, the policy source, the pinned domains, the urgency-only judge and the labels."""
        self._labels = labels
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
        if await mail_scope(mail, self._labels) is not Scope.IN_SCOPE:  # archived, excluded or unclear: not ours
            return
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

    async def _decide(
        self, mail: FetchedMail, current: JudgingList, ruled: RuleFiling | ExtraRule | RuleSkipped | None
    ) -> Outcome:
        """A sender rule files the mail without a category call; otherwise the model judges it."""
        trimmed = trim_mail(mail.subject, mail.sender, mail.text)
        if isinstance(ruled, RuleFiling):
            verdict = None if ruled.ticked else await self._urgency.needs_attention(trimmed)
            policy, now = await self._policy.current(), self._now()
            return with_always_notify(rule_outcome(ruled, verdict, mail, current, now, policy), current, now, policy)
        judged = await self._judge.judge(trimmed, current.categories, current.general_instructions)
        policy = await self._policy.current()  # one snapshot for this mail: the decision never mixes old and new values
        now = self._now()
        other = await self._labels.other()
        outcome = decide_outcome(judged, mail, current, now, policy, other_label=other.name)
        if isinstance(ruled, ExtraRule):  # the topic is the model's; the rule's extra label is added to it
            outcome = with_rule_extra(outcome, ruled)
        else:
            outcome = mark_not_applied(outcome, ruled if isinstance(ruled, RuleSkipped) else None)
        return with_always_notify(outcome, current, now, policy)

    async def _file(self, mail: FetchedMail, outcome: Outcome) -> None:
        outcome, label, label_id = await self._topic_label(mail, outcome)
        outcome = await self._add_extra(mail, outcome)
        await file_ensured(self._mail, self._labels, mail.message_id, label, label_id)
        await self._store.complete(mail.message_id, outcome)

    async def _topic_label(self, mail: FetchedMail, outcome: Outcome) -> tuple[Outcome, ManagedLabel, str]:
        label = await label_of(outcome, self._labels)
        try:
            return outcome, label, await ensure_id(self._mail, self._labels, label)
        except LabelRefused:  # the mailbox refuses this label: file under Other, never lose the mail or its alert
            logger.warning("label refused; filing under Other id=%s", mail.message_id)
            other = await self._labels.other()
            return replace(outcome, label=other.name), other, await ensure_id(self._mail, self._labels, other)

    async def _add_extra(self, mail: FetchedMail, outcome: Outcome) -> Outcome:
        """Add the extra label before the mail leaves the inbox; a refused label drops the extra, never the mail."""
        if outcome.extra_label is None or outcome.filing is None or outcome.filing.extra_id is None:
            return outcome
        extra = await self._labels.topic(outcome.filing.extra_id)
        try:
            label_id = await ensure_id(self._mail, self._labels, extra)
        except LabelRefused:
            logger.warning("extra label refused id=%s", mail.message_id)
            return replace(outcome, extra_label=None, filing=replace(outcome.filing, extra_id=None))
        used = await asyncio.to_thread(self._mail.add_label, mail.message_id, label_id)
        if used != label_id:
            await self._labels.remember(extra, used)
        return outcome
