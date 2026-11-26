"""The plan build: judge the mail in scope against the list and write the moves it would take (INT-008).

ADR-0056, ADR-0055, spec AC-9 to AC-11, AC-13, AC-17, AC-18, AC-33, AC-47, AC-53, AC-54.

No build starts by itself (spec D12): a list change or a first start creates no plan. A plan starts only from a
``resort_request`` row (the user pressed "Sort everything again"): the newest request without a plan gets a plan of its
own, and the database copies the threshold onto it. This use case then continues a plan that is ``building`` and
replaces a ``building`` or ``ready`` plan that a newer list outdated. It lists mail newest first, reads each mail once,
and writes an item only when the pair (topic, extra label) would change, with the confidence of the answer as a whole
percentage. A mail that a sender rule files is decided in code at confidence 100 without a model call. It spends only
the model budget above the reserve of ADR-0021; when that is used up the plan stays ``building`` and the next run
continues from the stored cursor. Nothing here moves or labels mail: the mailbox port has no write.

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
from app.core.judgement import OTHER_ID, ListedCategory, NeedsAttention, file_under
from app.core.managed import LabelRef, ManagedLabel, Role
from app.core.pinned import pinned_kind
from app.core.resort_plan import PlanKind, PlanState, build_may_start, kind_for, on_list_changed
from app.core.scope import Scope, classify, clean_display
from app.core.sender_rules import ExtraRule, RuleFiling, RuleSkipped, SenderRules
from app.usecases.catchup import BUDGET_RESERVE, CALLS_PER_MAIL

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail
    from app.adapters.judge_anthropic import TrimmedMail
    from app.core.judgement import Judgement
    from app.core.pinned import PinnedSenders
    from app.usecases.resort_apply import ResortLabels

__all__ = [
    "BUILD_SLICE",
    "PAGE_SIZE",
    "PLAN_CAP",
    "BuildList",
    "BuildResult",
    "BuildStatus",
    "BuildTips",
    "Candidate",
    "ItemDraft",
    "PlanNumbers",
    "PlanRecord",
    "ResortBuild",
    "ResortRequest",
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
    to_move: int  # items of the ``auto`` plan: they move on their own after the wait
    to_review: int  # items of the ``review`` plan: they wait for the user
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
    general_instructions: str = ""  # the owner's rules for the whole list: untrusted text for the model


@dataclass(frozen=True, slots=True)
class PlanRecord:
    """A plan and its build progress as stored."""

    plan_id: uuid.UUID
    list_version: int
    state: PlanState
    cursor: str | None
    checked: int
    unclear: int
    items: int  # items of the ``review`` plan, the plan this record stands for
    cap: int
    request_id: uuid.UUID | None = None  # the request the plan was made for; ``None`` for a plan of an older kind
    threshold: int | None = None  # copied from the request by the database; ``None`` without a request
    auto_items: int = 0  # items of the ``auto`` plan of the same request


@dataclass(frozen=True, slots=True)
class ResortRequest:
    """A "Sort everything again" request: its id and the confidence threshold the user typed (50 to 100)."""

    request_id: uuid.UUID
    threshold: int


@dataclass(frozen=True, slots=True)
class Candidate:
    """A listed mail and the opaque cursor that resumes the listing just after it."""

    message_id: str
    resume_after: str


@dataclass(frozen=True, slots=True)
class ItemDraft:
    """One planned move of a pair (topic, extra label), with only what the review page shows (AC-39: no body).

    ``confidence_pct`` is the model's own report as a whole percentage (100 for a sender rule).
    """

    message_id: str
    sender_name: str
    sender_address: str
    subject: str
    old_topic_id: uuid.UUID
    old_extra_id: uuid.UUID | None
    new_topic_id: uuid.UUID
    new_extra_id: uuid.UUID | None
    confidence_pct: int


class BuildMailbox(Protocol):
    """Gmail, read only. Blocking calls; run in a thread."""

    def label_names(self) -> dict[str, str]:
        """Label id to label name."""
        ...

    def estimate_in_scope(self) -> int:
        """A rough count of the mails the listing would return (an estimate, not exact)."""
        ...

    def candidates(self, after: str | None, limit: int) -> list[Candidate]:
        """List up to ``limit`` mails of the inbox or a managed label (not spam or trash).

        Newest first, strictly after the cursor ``after`` (``None`` starts at the top). The use case decides scope
        again by label id, so a listing that is too wide never plans mail of a label that is not managed.
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

    async def managed_labels(self) -> ResortLabels:
        """The managed labels now: the current list, the "Other" setting and the archive label (ADR-0060)."""
        ...

    async def latest_plan(self) -> PlanRecord | None:
        """The newest plan of the mailbox, terminal or not."""
        ...

    async def open_request(self) -> ResortRequest | None:
        """The newest request of the mailbox when no plan was made for it yet; older requests are never built."""
        ...

    async def start_plan(self, request: ResortRequest, list_version: int, cap: int) -> PlanRecord | None:
        """Insert the ``building`` ``review`` and ``auto`` plans of ``request``; ``None`` when one is open already.

        The returned record is the ``review`` plan; it carries the build progress of both.
        """
        ...

    async def replace_plan(self, plan_id: uuid.UUID) -> bool:
        """Compare-and-set ``building`` or ``ready`` to ``replaced`` and drop its items; its ``auto`` plan too."""
        ...

    async def record_estimate(self, plan_id: uuid.UUID, estimate: int) -> None:
        """Store the estimated number of mails in scope ("N of about M")."""
        ...

    async def complete_build(self, plan_id: uuid.UUID, *, not_looked_at: int) -> bool:
        """Compare-and-set ``building`` to ``ready``, store the not-looked-at count and approve the ``auto`` plan.

        One step: the ``auto`` plan goes ``ready`` and then ``scheduled`` through ``approve_system_plan``, or is dropped
        when it holds no item. True for the one caller.
        """
        ...

    async def rejected_ids(self, list_version: int) -> frozenset[str]:
        """Mail the user rejected under this list version (AC-13)."""
        ...

    async def record_progress(  # noqa: PLR0913
        self, plan_id: uuid.UUID, *, item: ItemDraft | None, kind: PlanKind, cursor: str, checked: int, unclear: int
    ) -> bool:
        """In one transaction add the item (to the plan of ``kind``), the counts and the cursor.

        False when the plan is no longer ``building``.
        """
        ...


class BuildNotifier(Protocol):
    """Telegram, plain note."""

    async def say(self, text: str) -> None:
        """Send a plain note."""
        ...


class BuildTips(Protocol):
    """The tips of a ready ``review`` plan (``PlanTips``)."""

    async def write(self, plan_id: uuid.UUID, categories: Sequence[ListedCategory]) -> int:
        """Store a tip per category with items below the threshold; how many were stored."""
        ...


class BudgetView(Protocol):
    """A read-only look at today's model budget."""

    def remaining(self) -> int:
        """Calls left today, reserve included."""
        ...


def plan_ready_text(numbers: PlanNumbers) -> str:
    """The notice: numbers and fixed words only, never a sender, subject or category name (AC-18)."""
    return (
        f"Sort again is ready: {numbers.checked} mails checked. {numbers.to_move} move on their own after the wait "
        f"(you can cancel before then), {numbers.to_review} wait for your review in the web app. "
        f"{numbers.unclear} unclear, {numbers.not_looked_at} not looked at."
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
        tips: BuildTips,
        budget: BudgetView,
        now: Callable[[], datetime],
        pinned: PinnedSenders,
        cap: int = PLAN_CAP,
        per_run: int = BUILD_SLICE,  # how many mails one run looks at before it pauses (ADR-0051)
    ) -> None:
        """Wire the ports, the clock and the allow-list of pinned sender domains."""
        self._mail = mailbox
        self._judge = judge
        self._store = store
        self._notifier = notifier
        self._tips = tips
        self._budget = budget
        self._now = now
        self._pinned = pinned
        self._cap = cap
        self._per_run = per_run

    async def run_once(self) -> BuildResult:
        """Replace an outdated plan, start the plan of a new request and work on the plan being built."""
        current = await self._store.current_list()
        if current.version == 0:
            return BuildResult(BuildStatus.IDLE)
        latest = await self._store.latest_plan()
        if latest is not None and latest.list_version != current.version and latest.state in _REPLACEABLE:
            if on_list_changed(latest.state).discard_decisions:
                await self._store.replace_plan(latest.plan_id)
            latest = await self._store.latest_plan()
        latest = await self._replace_for_new_request(latest)
        if latest is None or build_may_start(latest.state):
            latest = await self._start(current)
        if latest is None or not self._continues(latest, current):
            return BuildResult(BuildStatus.IDLE)
        return await self._build(latest, current)

    async def _replace_for_new_request(self, latest: PlanRecord | None) -> PlanRecord | None:
        """A newer request replaces the pending ``review`` plan (and its ``auto`` plan while that is still building)."""
        if latest is None or latest.state not in _REPLACEABLE:
            return latest
        request = await self._store.open_request()
        if request is None or request.request_id == latest.request_id:
            return latest
        await self._store.replace_plan(latest.plan_id)
        return await self._store.latest_plan()

    async def _start(self, current: BuildList) -> PlanRecord | None:
        """The plan of the newest request that has none; no request, no plan (D12)."""
        request = await self._store.open_request()
        if request is None:
            return None
        return await self._store.start_plan(request, current.version, self._cap)

    @staticmethod
    def _continues(latest: PlanRecord, current: BuildList) -> bool:
        return latest.state is PlanState.BUILDING and latest.list_version == current.version

    async def _build(self, plan: PlanRecord, current: BuildList) -> BuildResult:
        if plan.cursor is None:
            await self._store.record_estimate(plan.plan_id, await asyncio.to_thread(self._mail.estimate_in_scope))
        try:
            checked, unclear, review, auto, cursor = await self._scan(plan, current)
        except _Pause:
            return BuildResult(BuildStatus.PAUSED)
        except _Cancelled:
            return BuildResult(BuildStatus.CANCELLED)
        not_looked_at = await self._count_rest(cursor) if checked >= plan.cap else 0
        if not await self._store.complete_build(plan.plan_id, not_looked_at=not_looked_at):
            return BuildResult(BuildStatus.CANCELLED)
        numbers = PlanNumbers(checked, auto, review, unclear, not_looked_at)
        logger.info(
            "plans ready checked=%d auto=%d review=%d unclear=%d not_looked_at=%d",
            checked,
            auto,
            review,
            unclear,
            not_looked_at,
        )
        await self._notifier.say(plan_ready_text(numbers))
        await self._tips.write(plan.plan_id, current.categories)  # after the notice: a help, never part of the plan
        return BuildResult(BuildStatus.READY, numbers)

    async def _scan(self, plan: PlanRecord, current: BuildList) -> tuple[int, int, int, int, str | None]:
        """Look at the listed mail until the cap, the end or the slice.

        Return (checked, unclear, review items, auto items, cursor).

        After ``per_run`` mails the run pauses (the progress of each mail is already stored) and the next run goes on.
        """
        names = await asyncio.to_thread(self._mail.label_names)
        rejected = await self._store.rejected_ids(plan.list_version)
        lookup = _Lookup(current, await self._store.managed_labels())
        checked, unclear, review, auto, cursor = plan.checked, plan.unclear, plan.items, plan.auto_items, plan.cursor
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
                result = await self._look(plan, candidate, lookup, names, rejected)
                looked += 1
                cursor = candidate.resume_after
                checked, unclear = checked + result[0], unclear + result[1]
                review, auto = review + (result[2] is PlanKind.REVIEW), auto + (result[2] is PlanKind.AUTO)
        return checked, unclear, review, auto, cursor

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

    async def _look(
        self,
        plan: PlanRecord,
        candidate: Candidate,
        lookup: _Lookup,
        names: dict[str, str],
        rejected: frozenset[str],
    ) -> tuple[int, int, PlanKind | None]:
        """Look at one mail and write its progress; return (checked, unclear, the plan its item went to)."""
        item: ItemDraft | None = None
        checked = unclear = 0
        mail = (
            None
            if candidate.message_id in rejected
            else await asyncio.to_thread(self._mail.fetch, candidate.message_id)
        )
        if mail is not None:
            refs = [LabelRef(i, names.get(i, "")) for i in mail.labels]
            scope = classify(refs, lookup.labels.managed)
            if scope is Scope.UNCLEAR:
                checked = unclear = 1
            elif scope is Scope.IN_SCOPE and pinned_kind(mail.auth_results, mail.sender, self._pinned) is None:
                checked = 1
                item = await self._judged_item(mail, lookup, lookup.held(refs))
        kind = PlanKind.REVIEW if item is None else kind_for(item.confidence_pct, plan.threshold)
        if not await self._store.record_progress(
            plan.plan_id, item=item, kind=kind, cursor=candidate.resume_after, checked=checked, unclear=unclear
        ):
            raise _Cancelled
        return checked, unclear, None if item is None else kind

    async def _judged_item(self, mail: FetchedMail, lookup: _Lookup, labels: list[ManagedLabel]) -> ItemDraft | None:
        ruled = lookup.rules.apply(mail.auth_results, mail.sender)
        if isinstance(ruled, RuleFiling):  # decided in code: no model call, no budget (ADR-0054, ADR-0055)
            target = _Target(ruled.topic.category_id, _id_of(ruled.extra), CERTAIN)
        else:
            target = await self._judged_target(mail, lookup, ruled)
        return None if target is None else _draft(mail, lookup, labels, target)

    async def _judged_target(
        self, mail: FetchedMail, lookup: _Lookup, ruled: ExtraRule | RuleSkipped | None
    ) -> _Target | None:
        if self._budget.remaining() < BUDGET_RESERVE + CALLS_PER_MAIL:
            raise _Pause
        try:
            verdict = await self._judge.judge(
                trim_mail(mail.subject, mail.sender, mail.text), lookup.categories, lookup.instructions
            )
        except ModelUnavailable:
            logger.warning("model unavailable; the plan build continues next run")
            raise _Pause from None
        if isinstance(verdict, NeedsAttention):
            if verdict.reason == "budget":
                raise _Pause
            return None  # no trustworthy answer: the mail stays where it is
        filing = file_under(verdict, lookup.categories, other_label=lookup.other_name)
        extra = _id_of(ruled.extra) if isinstance(ruled, ExtraRule) else _id_of(filing.extra)
        return _Target(filing.category_id, extra, _percent(verdict.confidence))


_REPLACEABLE = frozenset({PlanState.BUILDING, PlanState.READY})
CERTAIN = 100  # the confidence of a sender rule: it is code, not a guess


@dataclass(frozen=True, slots=True)
class _Target:
    """The pair a mail should carry and how sure the answer was."""

    topic_id: str
    extra_id: str | None
    confidence_pct: int


class _Lookup:
    """The list of this run: the managed labels, the sender rules and the instructions."""

    def __init__(self, current: BuildList, labels: ResortLabels) -> None:
        self.categories = current.categories
        self.instructions = current.general_instructions
        self.rules = SenderRules(current.categories)
        self.labels = labels
        self.other_name = labels.by_category[OTHER_ID].name  # the "Other" setting
        self.category_of = {label: cid for cid, label in labels.by_category.items()}

    def held(self, refs: list[LabelRef]) -> list[ManagedLabel]:
        """The managed labels a mail carries; the labels of the user are not part of its pair."""
        found = (self.labels.managed.find(ref) for ref in refs)
        return [label for label in found if label is not None]


def _id_of(category: ListedCategory | None) -> str | None:
    return None if category is None else category.category_id


def _percent(confidence: float) -> int:
    """The validated 0 to 1 confidence as a whole percentage; the model's text never sets it any other way."""
    return max(0, min(100, round(confidence * 100)))


def _draft(mail: FetchedMail, lookup: _Lookup, labels: list[ManagedLabel], target: _Target) -> ItemDraft | None:
    """An item only when the pair would change; mail without a topic label counts as Other."""
    topic_label = next((label for label in labels if label.role is not Role.EXTRA), None)
    extra_label = next((label for label in labels if label.role is Role.EXTRA), None)
    old_topic = lookup.category_of.get(topic_label, OTHER_ID) if topic_label else OTHER_ID
    old_extra = lookup.category_of.get(extra_label) if extra_label else None
    if (old_topic, old_extra) == (target.topic_id, target.extra_id):
        return None
    name, _address = parseaddr(mail.headers.get("From", ""))
    name = clean_display(name, NAME_MAX)
    return ItemDraft(
        message_id=mail.message_id,
        sender_name=name,
        sender_address=clean_display(mail.sender, ADDRESS_MAX),
        subject=clean_display(mail.subject, SUBJECT_MAX),
        old_topic_id=uuid.UUID(old_topic),
        old_extra_id=None if old_extra is None else uuid.UUID(old_extra),
        new_topic_id=uuid.UUID(target.topic_id),
        new_extra_id=None if target.extra_id is None else uuid.UUID(target.extra_id),
        confidence_pct=target.confidence_pct,
    )
