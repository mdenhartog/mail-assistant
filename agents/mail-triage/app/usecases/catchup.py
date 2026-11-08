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
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003  # a dataclass field
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

from app.adapters.judge_anthropic import ModelUnavailable, trim_mail
from app.core.judgement import NeedsAttention
from app.usecases.triage import MAX_ATTEMPTS, Claim, RunSummary, decide_outcome

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.gmail_read import FetchedMail
    from app.core.judgement import Judgement
    from app.usecases.triage import FailureNotifier, Outcome

logger = logging.getLogger(__name__)

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

    def ensure_label(self, name: str) -> str:
        """Id of the label, created when missing."""
        ...

    def file(self, message_id: str, label_id: str) -> None:
        """Add the category label and remove the inbox label."""
        ...


class CatchUpJudge(Protocol):
    """The model adapter."""

    async def judge(self, mail: object) -> Judgement | NeedsAttention:
        """A valid judgement, or needs-attention."""
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

    async def known_labels(self) -> list[str]:
        """Category labels in use."""
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
    ) -> None:
        """Wire the ports, the budget view and the clock."""
        self._mail = mailbox
        self._judge = judge
        self._store = store
        self._notifier = notifier
        self._budget = budget
        self._now = now

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
        if await self._store.claim(mail.message_id, mail.thread_id) is Claim.DONE:
            return _Step.SKIPPED
        verdict = await self._judge.judge(trim_mail(mail.subject, mail.sender, mail.text))
        if isinstance(verdict, NeedsAttention) and verdict.reason == "budget":
            return _Step.STOP  # an old mail is never filed as "needs attention" only because the budget ended
        outcome = decide_outcome(verdict, mail, await self._store.known_labels(), self._now())
        label_id = await asyncio.to_thread(self._mail.ensure_label, outcome.label)
        await asyncio.to_thread(self._mail.file, mail.message_id, label_id)
        await self._store.complete_backlog(mail.message_id, outcome)
        summary.filed += 1
        summary.alerts += outcome.alert is not None
        return _Step.HANDLED
