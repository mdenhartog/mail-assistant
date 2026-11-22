"""The plan build: judge the mail in scope against the current list and write the moves it would take (INT-004).

ADR-0046 point 3, spec AC-9, AC-10, AC-11, AC-13, AC-17, AC-18, AC-33, AC-52, AC-54.

No build starts by itself (spec D12): a list change or a first start creates no plan. This use case only continues a
plan that is ``building`` and replaces a ``building`` or ``ready`` plan that a newer list outdated. It lists mail
newest first, reads each mail once, and writes an item only when the category would change. It spends only the model
budget above the reserve of ADR-0021; when that is used up the plan stays ``building`` and the next run continues from
the stored cursor. Nothing here moves or labels mail: the mailbox port has no write.

Every write of progress is one compare-and-set on the plan, so a plan that was replaced meanwhile gets no more items.
The notice holds numbers only (AC-18); logs hold ids and counts, never mail text.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from email.utils import parseaddr
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from app.adapters.judge_anthropic import ModelUnavailable, trim_mail
from app.core.judgement import OTHER_ID, Filing, ListedCategory, NeedsAttention, resolve
from app.core.resort_plan import PlanState, on_list_changed
from app.core.scope import LABEL_PREFIX, Scope, assistant_labels, classify, clean_display
from app.usecases.catchup import BUDGET_RESERVE, CALLS_PER_MAIL
from app.usecases.triage import pinned_mail_kind

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail
    from app.adapters.judge_anthropic import TrimmedMail
    from app.core.judgement import Judgement
    from app.core.pinned import PinnedSenders

__all__ = [
    "BUILD_SLICE",
    "PAGE_SIZE",
    "PLAN_CAP",
    "BuildList",
    "BuildResult",
    "BuildStatus",
    "Candidate",
    "ItemDraft",
    "PlanNumbers",
    "PlanRecord",
    "ResortBuild",
    "plan_ready_text",
]

logger = logging.getLogger(__name__)

PLAN_CAP = 5000  # mails a plan looks at, newest first (D15)
PAGE_SIZE = 100
# Mails one run looks at before it gives the cycle back (ADR-0051). At about 2 to 3 seconds per judged mail this is
# under a minute, so alerts, the overview and the heartbeat (180 seconds) are never kept waiting by a long build.
BUILD_SLICE = 20
SUBJECT_MAX = 120
NAME_MAX = 120
ADDRESS_MAX = 320


class BuildStatus(StrEnum):
    """How a run ended."""

    IDLE = "idle"  # nothing to build
    PAUSED = "paused"  # budget or model: the plan stays building and continues next run
    CANCELLED = "cancelled"  # a newer list replaced the plan under construction
    READY = "ready"


@dataclass(frozen=True, slots=True)
class PlanNumbers:
    """The counts the notice carries."""

    checked: int
    to_move: int
    unclear: int
    not_looked_at: int


@dataclass(frozen=True, slots=True)
class BuildResult:
    """The outcome of one run; ``numbers`` only when a plan became ready."""

    status: BuildStatus
    numbers: PlanNumbers | None = None


@dataclass(frozen=True, slots=True)
class BuildList:
    """The current list version, when it was saved, and its categories."""

    version: int  # 0 before the first version exists
    changed_at: datetime
    categories: tuple[ListedCategory, ...]
    general_instructions: str = ""  # filled by the plan-build reader of a later unit; empty until then


@dataclass(frozen=True, slots=True)
class PlanRecord:
    """A plan and its build progress as stored."""

    plan_id: uuid.UUID
    list_version: int
    state: PlanState
    cursor: str | None
    checked: int
    unclear: int
    items: int
    cap: int


@dataclass(frozen=True, slots=True)
class Candidate:
    """A listed mail and the opaque cursor that resumes the listing just after it."""

    message_id: str
    resume_after: str


@dataclass(frozen=True, slots=True)
class ItemDraft:
    """One planned move, with only what the review page shows (AC-39: no body)."""

    message_id: str
    sender_name: str
    sender_address: str
    subject: str
    old_category_id: uuid.UUID
    new_category_id: uuid.UUID


class BuildMailbox(Protocol):
    """Gmail, read only. Blocking calls; run in a thread."""

    def label_names(self) -> dict[str, str]:
        """Label id to label name."""
        ...

    def estimate_in_scope(self) -> int:
        """A rough count of the mails the listing would return (an estimate, not exact)."""
        ...

    def candidates(self, after: str | None, limit: int) -> list[Candidate]:
        """List up to ``limit`` mails of the inbox or an ``Assistant/`` label (not spam or trash).

        Newest first, strictly after the cursor ``after`` (``None`` starts at the top).
        """
        ...

    def fetch(self, message_id: str) -> FetchedMail | None:
        """Headers, text and label ids of one mail; ``None`` when it no longer exists."""
        ...


class BuildJudge(Protocol):
    """The model adapter of the judging code."""

    async def judge(
        self, mail: TrimmedMail, categories: Sequence[ListedCategory], instructions: str
    ) -> Judgement | NeedsAttention:
        """A valid judgement for this one mail, or needs-attention."""
        ...


class BuildStore(Protocol):
    """The plan tables as the build needs them."""

    async def current_list(self) -> BuildList:
        """The latest list version."""
        ...

    async def latest_plan(self) -> PlanRecord | None:
        """The newest plan of the mailbox, terminal or not."""
        ...

    async def replace_plan(self, plan_id: uuid.UUID) -> bool:
        """Compare-and-set ``building`` or ``ready`` to ``replaced`` and drop its items."""
        ...

    async def record_estimate(self, plan_id: uuid.UUID, estimate: int) -> None:
        """Store the estimated number of mails in scope ("N of about M")."""
        ...

    async def complete_build(self, plan_id: uuid.UUID, *, not_looked_at: int) -> bool:
        """Compare-and-set ``building`` to ``ready`` and store the not-looked-at count; true for the one caller."""
        ...

    async def rejected_ids(self, list_version: int) -> frozenset[str]:
        """Mail the user rejected under this list version (AC-13)."""
        ...

    async def record_progress(
        self, plan_id: uuid.UUID, *, item: ItemDraft | None, cursor: str, checked: int, unclear: int
    ) -> bool:
        """In one transaction add the item, the counts and the cursor; false when the plan is no longer ``building``."""
        ...


class BuildNotifier(Protocol):
    """Telegram, plain note."""

    async def say(self, text: str) -> None:
        """Send a plain note."""
        ...


class BudgetView(Protocol):
    """A read-only look at today's model budget."""

    def remaining(self) -> int:
        """Calls left today, reserve included."""
        ...


def plan_ready_text(numbers: PlanNumbers) -> str:
    """The notice: numbers and fixed words only, never a sender, subject or category name (AC-18)."""
    return (
        f"Plan ready: {numbers.checked} mails checked, {numbers.to_move} to move, "
        f"{numbers.unclear} unclear, {numbers.not_looked_at} not looked at. Review it in the web app."
    )


class _Pause(Exception):  # noqa: N818 - control flow inside this module only
    """The budget or the model stops this run; the plan continues next run."""


class _Cancelled(Exception):  # noqa: N818 - control flow inside this module only
    """The plan is no longer ``building``."""


class ResortBuild:
    """Builds the plan for the current list, a bit at a time."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        mailbox: BuildMailbox,
        judge: BuildJudge,
        store: BuildStore,
        notifier: BuildNotifier,
        budget: BudgetView,
        now: Callable[[], datetime],
        pinned: PinnedSenders,
        archive_label: str,  # the protected label (C-14, ADR-0052)
        cap: int = PLAN_CAP,
        per_run: int = BUILD_SLICE,  # how many mails one run looks at before it pauses (ADR-0051)
    ) -> None:
        """Wire the ports, the clock and the allow-list of pinned sender domains."""
        self._mail = mailbox
        self._judge = judge
        self._store = store
        self._notifier = notifier
        self._budget = budget
        self._now = now
        self._pinned = pinned
        self._archive = archive_label
        self._cap = cap
        self._per_run = per_run

    async def run_once(self) -> BuildResult:
        """Replace a plan that a newer list outdated and work on the plan being built; never start a plan."""
        current = await self._store.current_list()
        if current.version == 0:
            return BuildResult(BuildStatus.IDLE)
        latest = await self._store.latest_plan()
        if latest is not None and latest.list_version != current.version and latest.state in _REPLACEABLE:
            if on_list_changed(latest.state).discard_decisions:
                await self._store.replace_plan(latest.plan_id)
            latest = await self._store.latest_plan()
        if latest is None or not self._continues(latest, current):
            return BuildResult(BuildStatus.IDLE)
        return await self._build(latest, current)

    @staticmethod
    def _continues(latest: PlanRecord, current: BuildList) -> bool:
        return latest.state is PlanState.BUILDING and latest.list_version == current.version

    async def _build(self, plan: PlanRecord, current: BuildList) -> BuildResult:
        if plan.cursor is None:
            await self._store.record_estimate(plan.plan_id, await asyncio.to_thread(self._mail.estimate_in_scope))
        try:
            checked, unclear, items, cursor = await self._scan(plan, current)
        except _Pause:
            return BuildResult(BuildStatus.PAUSED)
        except _Cancelled:
            return BuildResult(BuildStatus.CANCELLED)
        not_looked_at = await self._count_rest(cursor) if checked >= plan.cap else 0
        if not await self._store.complete_build(plan.plan_id, not_looked_at=not_looked_at):
            return BuildResult(BuildStatus.CANCELLED)
        numbers = PlanNumbers(checked, items, unclear, not_looked_at)
        logger.info(
            "plan ready checked=%d items=%d unclear=%d not_looked_at=%d", checked, items, unclear, not_looked_at
        )
        await self._notifier.say(plan_ready_text(numbers))
        return BuildResult(BuildStatus.READY, numbers)

    async def _scan(self, plan: PlanRecord, current: BuildList) -> tuple[int, int, int, str | None]:
        """Look at the listed mail until the cap, the end or the slice; return (checked, unclear, items, cursor).

        After ``per_run`` mails the run pauses (the progress of each mail is already stored) and the next run goes on.
        """
        names = await asyncio.to_thread(self._mail.label_names)
        rejected = await self._store.rejected_ids(plan.list_version)
        by_label = {f"{LABEL_PREFIX}{c.name.strip()}": c.category_id for c in current.categories}
        checked, unclear, items, cursor = plan.checked, plan.unclear, plan.items, plan.cursor
        looked = 0
        while checked < plan.cap:
            page = await asyncio.to_thread(self._mail.candidates, cursor, PAGE_SIZE)
            if not page:
                break
            for candidate in page:
                if checked >= plan.cap:
                    break
                if looked >= self._per_run:
                    raise _Pause
                await self._still_current(plan)
                result = await self._look(plan, candidate, current, names, rejected, by_label)
                looked += 1
                cursor = candidate.resume_after
                checked, unclear, items = checked + result[0], unclear + result[1], items + result[2]
        return checked, unclear, items, cursor

    async def _still_current(self, plan: PlanRecord) -> None:
        """A newer list outdates the plan at once: replace it and stop before another mail is judged (AC-33)."""
        if (await self._store.current_list()).version != plan.list_version:
            await self._store.replace_plan(plan.plan_id)
            raise _Cancelled

    async def _count_rest(self, cursor: str | None) -> int:
        count = 0
        while page := await asyncio.to_thread(self._mail.candidates, cursor, PAGE_SIZE):
            count += len(page)
            cursor = page[-1].resume_after
        return count

    async def _look(  # noqa: PLR0913, PLR0917
        self,
        plan: PlanRecord,
        candidate: Candidate,
        current: BuildList,
        names: dict[str, str],
        rejected: frozenset[str],
        by_label: dict[str, str],
    ) -> tuple[int, int, int]:
        """Look at one mail and write its progress; return (checked, unclear, items) added."""
        item: ItemDraft | None = None
        checked = unclear = 0
        mail = (
            None
            if candidate.message_id in rejected
            else await asyncio.to_thread(self._mail.fetch, candidate.message_id)
        )
        if mail is not None:
            label_names = {names[i] for i in mail.labels if i in names}
            scope = classify(label_names, self._archive)
            if scope is Scope.UNCLEAR:
                checked = unclear = 1
            elif scope is Scope.IN_SCOPE and pinned_mail_kind(mail, self._pinned) is None:
                checked = 1
                item = await self._judged_item(mail, current, assistant_labels(label_names), by_label)
        if not await self._store.record_progress(
            plan.plan_id, item=item, cursor=candidate.resume_after, checked=checked, unclear=unclear
        ):
            raise _Cancelled
        return checked, unclear, item is not None

    async def _judged_item(
        self, mail: FetchedMail, current: BuildList, labels: list[str], by_label: dict[str, str]
    ) -> ItemDraft | None:
        if self._budget.remaining() < BUDGET_RESERVE + CALLS_PER_MAIL:
            raise _Pause
        try:
            verdict = await self._judge.judge(
                trim_mail(mail.subject, mail.sender, mail.text), current.categories, current.general_instructions
            )
        except ModelUnavailable:
            logger.warning("model unavailable; the plan build continues next run")
            raise _Pause from None
        if isinstance(verdict, NeedsAttention) and verdict.reason == "budget":
            raise _Pause
        filing = resolve(verdict, current.categories) if not isinstance(verdict, NeedsAttention) else verdict
        if isinstance(filing, NeedsAttention):
            return None  # no trustworthy category: the mail stays where it is
        return _draft(mail, filing, labels, by_label)


_REPLACEABLE = frozenset({PlanState.BUILDING, PlanState.READY})


def _draft(mail: FetchedMail, filing: Filing, labels: list[str], by_label: dict[str, str]) -> ItemDraft | None:
    """An item only when the category would change; a label outside the list (a deleted category) always moves."""
    label = labels[0] if labels else None
    old_id = by_label.get(label, OTHER_ID) if label else OTHER_ID
    legacy = label is not None and label not in by_label
    if filing.category_id == old_id and not legacy:
        return None
    name, _address = parseaddr(mail.headers.get("From", ""))
    name = clean_display(name, NAME_MAX)
    return ItemDraft(
        message_id=mail.message_id,
        sender_name=name,
        sender_address=clean_display(mail.sender, ADDRESS_MAX),
        subject=clean_display(mail.subject, SUBJECT_MAX),
        old_category_id=uuid.UUID(old_id),
        new_category_id=uuid.UUID(filing.category_id),
    )
