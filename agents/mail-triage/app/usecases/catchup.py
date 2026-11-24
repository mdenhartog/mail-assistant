"""The one-time catch-up of the unread mail that was already in the inbox (INT-003, ADR-0021).

Each mail cycle first handles new mail (the pipeline). Then this use case works through the unread inbox mail from
before the cut-off, newest first, with the same judging and labelling as new mail. The cut-off and "done" are the
only things stored: Gmail is the list, because a filed mail loses its inbox label and so drops out of the next
listing.

Logs and notices hold counts and ids only, never mail text (spec AC-B13).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime  # noqa: TC003  # a dataclass field
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

from app.adapters.judge_anthropic import ModelUnavailable, trim_mail
from app.core.judgement import NeedsAttention
from app.core.scope import Scope
from app.usecases.triage import (
    MAX_ATTEMPTS,
    Claim,
    RunSummary,
    decide_outcome,
    file_under_label,
    label_of,
    mail_scope,
    pinned_mail_kind,
    pinned_outcome,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from app.adapters.gmail_read import FetchedMail
    from app.adapters.judge_anthropic import TrimmedMail
    from app.core.judgement import Judgement, JudgingList, ListedCategory
    from app.core.managed import ManagedLabel
    from app.core.pinned import PinnedSenders
    from app.usecases.policy_notice import PolicySource
    from app.usecases.triage import FailureNotifier, LabelBook, Outcome

logger = logging.getLogger(__name__)

BACKLOG_ALERT_LIMIT = 5  # alerts the whole catch-up may create; urgent mail beyond it goes to the daily overview
RUN_LIMIT = 20  # mails per run, so one run stays short and the minute cycle keeps serving new mail and Telegram
BUDGET_RESERVE = 50  # model calls a day that stay for new mail (of the 200); fixed in code, like the quiet hours
CALLS_PER_MAIL = 2  # the small model, and the large one when the small one is unsure
INBOX = "INBOX"
UNREAD = "UNREAD"


@dataclass(frozen=True, slots=True)
class CatchUpState:
    """When the catch-up started (the cut-off) and, once it is done, when it finished."""

    started_at: datetime
    finished_at: datetime | None


class _Step(Enum):
    SKIPPED = auto()  # not processed and nothing to retry: read meanwhile, or already filed
    HANDLED = auto()  # filed, or failed and counted
    STOP = auto()  # the model is down: leave the rest for the next run


class CatchUpMailbox(Protocol):
    """Gmail as the catch-up needs it. Blocking calls; run in a thread."""

    def list_unread_before(self, cutoff: datetime) -> list[str]:
        """Ids of unread inbox mails older than ``cutoff``, newest first."""
        ...

    def fetch(self, message_id: str) -> FetchedMail:
        """Headers, text and labels of one mail."""
        ...

    def ensure_label(self, label: ManagedLabel) -> str:
        """Id of the managed label, created when missing."""
        ...

    def file(self, message_id: str, label_id: str) -> str:
        """Add the managed label and remove the inbox label; the id used comes back (new when it was recreated)."""
        ...


class CatchUpJudge(Protocol):
    """The model adapter."""

    async def judge(
        self, mail: TrimmedMail, categories: Sequence[ListedCategory], instructions: str
    ) -> Judgement | NeedsAttention:
        """A valid judgement for this one mail against ``categories``, or needs-attention."""
        ...


class CatchUpStore(Protocol):
    """Persistence as the catch-up needs it."""

    async def catchup_state(self) -> CatchUpState | None:
        """The stored state, or ``None`` before the first run."""
        ...

    async def start_catchup(self, at: datetime) -> None:
        """Store the cut-off; keeps the first one."""
        ...

    async def finish_catchup(self, at: datetime) -> None:
        """Mark the catch-up done."""
        ...

    async def claim(self, message_id: str, thread_id: str) -> Claim:
        """Claim a mail: ``NEW`` for the first caller only."""
        ...

    async def current_list(self) -> JudgingList:
        """The latest list version with its categories."""
        ...

    async def complete_backlog(self, message_id: str, outcome: Outcome) -> None:
        """Record the outcome of an old mail."""
        ...

    async def backlog_alerts(self) -> int:
        """How many alerts the catch-up created."""
        ...

    async def record_failure(self, message_id: str) -> int:
        """Count one more failed attempt and return the total."""
        ...

    async def abandon(self, message_id: str) -> None:
        """Stop retrying this mail."""
        ...


class BudgetView(Protocol):
    """A read-only look at today's model budget."""

    def remaining(self) -> int:
        """Calls left today."""
        ...


class CatchUp:
    """Works through the old unread mail, a few at a time, and finishes once."""

    def __init__(  # noqa: PLR0913, PLR0917 - every part is injected for tests
        self,
        mailbox: CatchUpMailbox,
        judge: CatchUpJudge,
        store: CatchUpStore,
        notifier: FailureNotifier,
        budget: BudgetView,
        now: Callable[[], datetime],
        policy: PolicySource,
        pinned: PinnedSenders,
        labels: LabelBook,
    ) -> None:
        """Wire the ports, the budget view, the clock, the policy source, the security domains and the labels."""
        self._labels = labels
        self._pinned = pinned
        self._mail = mailbox
        self._judge = judge
        self._store = store
        self._notifier = notifier
        self._budget = budget
        self._now = now
        self._policy = policy

    async def run_once(self) -> RunSummary:
        """One run: start when needed, file up to ``RUN_LIMIT`` old mails, finish when none is left."""
        summary = RunSummary()
        state = await self._store.catchup_state()
        if state is None:
            await self._store.start_catchup(self._now())
            state = await self._store.catchup_state()
        if state is None or state.finished_at is not None:
            return summary
        try:
            ids = await asyncio.to_thread(self._mail.list_unread_before, state.started_at)
        except Exception as error:
            logger.warning("catch-up listing failed kind=%s", type(error).__name__)
            summary.listing_failed = True
            return summary
        processed = 0
        for message_id in ids:
            if processed >= RUN_LIMIT or self._budget.remaining() < BUDGET_RESERVE + CALLS_PER_MAIL:
                return summary  # the rest waits: for the next run, or for tomorrow's budget
            step = await self._step(message_id, summary)
            if step is _Step.STOP:
                return summary
            processed += step is _Step.HANDLED
        if summary.retry_later == 0:
            await self._store.finish_catchup(self._now())
        return summary

    async def _step(self, message_id: str, summary: RunSummary) -> _Step:
        try:
            mail = await asyncio.to_thread(self._mail.fetch, message_id)
        except Exception as error:  # nothing is claimed yet, so there is no row to count the failure on
            logger.warning("catch-up fetch failed id=%s kind=%s", message_id, type(error).__name__)
            summary.retry_later += 1
            return _Step.HANDLED
        try:
            return await self._file_one(mail, summary)
        except ModelUnavailable:
            logger.warning("model unavailable; leaving the remaining old mail for the next run")
            summary.model_down = True
            summary.retry_later += 1
            return _Step.STOP
        except Exception as error:
            logger.warning("catch-up failed id=%s kind=%s", message_id, type(error).__name__)
            await self._fail(message_id, summary)
            return _Step.HANDLED

    async def _fail(self, message_id: str, summary: RunSummary) -> None:
        attempts = await self._store.record_failure(message_id)
        if attempts < MAX_ATTEMPTS:
            summary.retry_later += 1
        elif attempts == MAX_ATTEMPTS:  # the one notice
            await self._store.abandon(message_id)
            await self._notifier.notify_failure(message_id)
            summary.given_up += 1

    async def _file_one(self, mail: FetchedMail, summary: RunSummary) -> _Step:
        if not {INBOX, UNREAD} <= mail.labels:  # read or moved since the listing: not ours to touch (AC-B2)
            return _Step.SKIPPED
        if await mail_scope(mail, self._labels) is not Scope.IN_SCOPE:  # archived, excluded or unclear: not ours
            return _Step.SKIPPED
        if await self._store.claim(mail.message_id, mail.thread_id) is Claim.DONE:
            return _Step.SKIPPED
        kind = pinned_mail_kind(mail, self._pinned)  # pinned mail stays in the inbox, whatever its age (AC-39)
        if kind is not None:
            outcome = pinned_outcome(kind, mail, self._now(), await self._policy.current())
            await self._complete_capped(mail, outcome, summary)
            return _Step.HANDLED
        current = await self._store.current_list()
        verdict = await self._judge.judge(
            trim_mail(mail.subject, mail.sender, mail.text), current.categories, current.general_instructions
        )
        if isinstance(verdict, NeedsAttention) and verdict.reason == "budget":
            return _Step.STOP  # an old mail is never filed as "needs attention" only because the budget ended
        policy = await self._policy.current()  # one snapshot for this mail
        other = await self._labels.other()
        outcome = decide_outcome(verdict, mail, current, self._now(), policy, other_label=other.name)
        outcome = await self._capped(outcome)
        await file_under_label(self._mail, self._labels, mail.message_id, await label_of(outcome, self._labels))
        await self._store.complete_backlog(mail.message_id, outcome)
        summary.filed += 1
        summary.alerts += outcome.alert is not None
        return _Step.HANDLED

    async def _capped(self, outcome: Outcome) -> Outcome:
        if outcome.alert is not None and await self._store.backlog_alerts() >= BACKLOG_ALERT_LIMIT:
            return replace(outcome, alert=None, release_at=None)  # still urgent, so the overview lists it (C-B5)
        return outcome

    async def _complete_capped(self, mail: FetchedMail, outcome: Outcome, summary: RunSummary) -> None:
        outcome = await self._capped(outcome)
        await self._store.complete_backlog(mail.message_id, outcome)
        summary.alerts += outcome.alert is not None
