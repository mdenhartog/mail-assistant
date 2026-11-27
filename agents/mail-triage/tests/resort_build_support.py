"""Doubles for the plan build tests: an in-memory plan store, a Gmail-backed mailbox view, a scripted judge."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.adapters.gmail_read import FetchedMail
from app.core.judgement import (
    OTHER_ID,
    Judgement,
    JudgementError,
    ListedCategory,
    NeedsAttention,
    parse_judgement,
)
from app.core.managed import ManagedLabel, ManagedSet, Role
from app.core.pinned import PinnedSenders
from app.core.resort_plan import PlanKind, PlanState
from app.usecases.resort_apply import ResortLabels
from app.usecases.resort_build import BuildList, Candidate, ItemDraft, PlanRecord, ResortBuild, ResortRequest
from category_policy.kinds import Kind
from tests.fakes.budget_ledger import BudgetLedger
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.fake_telegram import FakeTelegram

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from app.adapters.judge_anthropic import TrimmedMail

OTHER_NAME = "Other"  # the default of the "Other" setting
ARCHIVE_NAME = "Archive"  # the default of the archive setting


START = datetime(2026, 11, 15, 9, 0, tzinfo=UTC)
FINANCE = "00000000-0000-0000-0000-00000000000a"
TRAVEL = "00000000-0000-0000-0000-00000000000b"
CATEGORIES = (
    ListedCategory(FINANCE, "Finance", "Bills and invoices"),
    ListedCategory(TRAVEL, "Travel", "Tickets and bookings"),
)
PINNED = PinnedSenders(google_security=frozenset({"accounts.google.com"}), sign_in=frozenset({"mail.example.test"}))
DAILY_TOTAL = 100
RESERVE = 50


def resort_labels(  # noqa: PLR0913
    gmail: FakeGmail,
    categories: Sequence[ListedCategory],
    *,
    stored: dict[str, str] | None = None,
    other: str = OTHER_NAME,
    archive: str = ARCHIVE_NAME,
    extras: frozenset[str] = frozenset(),
    writes_held: bool = False,
) -> ResortLabels:
    """The managed labels as the database would hold them: a stored id wins, else the Gmail label of that name.

    ``stored`` maps a category id (``OTHER_ID`` for "Other", ``"archive"`` for the archive label) to the label id
    the database stored for it. ``extras`` lists category ids that are extra labels. ``writes_held`` is the rename
    plan that is not done: the set carries the hold and only a stored id counts (no label is found by its name).
    """
    ids = {} if writes_held else {name: label_id for label_id, name in gmail.label_table.items()}
    kept = stored or {}
    by_category: dict[str, ManagedLabel] = {}
    for category in categories:
        name = category.name.strip()
        role = Role.EXTRA if category.kind is Kind.EXTRA or category.category_id in extras else Role.TOPIC
        by_category[category.category_id] = ManagedLabel(name, kept.get(category.category_id) or ids.get(name), role)
    by_category[OTHER_ID] = ManagedLabel(other, kept.get(OTHER_ID) or ids.get(other), Role.OTHER)
    archive_label = ManagedLabel(archive, kept.get("archive") or ids.get(archive), Role.ARCHIVE)
    return ResortLabels(ManagedSet([*by_category.values(), archive_label], writes_held=writes_held), by_category)


class FakeBuildStore:
    """The plan tables in memory. A plan that is not ``building`` refuses progress, like the compare-and-set."""

    def __init__(self, clock: FakeClock, gmail: FakeGmail | None = None) -> None:
        self._clock = clock
        self._gmail = FakeGmail() if gmail is None else gmail
        self.stored_ids: dict[str, str] = {}
        self.other_name = OTHER_NAME
        self.writes_held = False  # the rename plan is not done (R4)
        self.list = BuildList(version=1, changed_at=clock(), categories=CATEGORIES)
        self.plans: list[PlanRecord] = []
        self.items: dict[uuid.UUID, list[ItemDraft]] = {}
        self.rejections: dict[str, int] = {}  # message id -> list version
        self.estimates: dict[uuid.UUID, int] = {}
        self.not_looked_at: dict[uuid.UUID, int] = {}
        self.requests: list[ResortRequest] = []
        self.planned: set[uuid.UUID] = set()  # requests that have a plan
        # The auto plan of each request, by the id of its review plan (``plans`` holds the review plans).
        self.auto_state: dict[uuid.UUID, PlanState] = {}
        self.auto: dict[uuid.UUID, list[ItemDraft]] = {}

    def save_list(self, categories: Sequence[ListedCategory] = CATEGORIES) -> None:
        """The user saves a new list version now."""
        self.list = BuildList(self.list.version + 1, self._clock(), tuple(categories))

    def reject(self, message_id: str, version: int | None = None) -> None:
        self.rejections[message_id] = self.list.version if version is None else version

    def plan(self, index: int = -1) -> PlanRecord:
        return self.plans[index]

    def items_of(self, plan: PlanRecord) -> list[ItemDraft]:
        """Every item the build wrote for the request of ``plan``, in both plans."""
        return [*self.auto.get(plan.plan_id, []), *self.items.get(plan.plan_id, [])]

    def auto_items_of(self, plan: PlanRecord) -> list[ItemDraft]:
        return self.auto.get(plan.plan_id, [])

    def review_items_of(self, plan: PlanRecord) -> list[ItemDraft]:
        return self.items.get(plan.plan_id, [])

    async def current_list(self) -> BuildList:
        return self.list

    async def managed_labels(self) -> ResortLabels:
        return resort_labels(
            self._gmail,
            self.list.categories,
            stored=self.stored_ids,
            other=self.other_name,
            writes_held=self.writes_held,
        )

    async def latest_plan(self) -> PlanRecord | None:
        return self.plans[-1] if self.plans else None

    def add_request(self, threshold: int = 50) -> ResortRequest:
        """The api writes a "Sort everything again" request."""
        request = ResortRequest(uuid.uuid4(), threshold)
        self.requests.append(request)
        return request

    async def open_request(self) -> ResortRequest | None:
        """The latest request, when no plan was made for it yet."""
        if not self.requests or self.requests[-1].request_id in self.planned:
            return None
        return self.requests[-1]

    async def start_plan(self, request: ResortRequest, list_version: int, cap: int) -> PlanRecord | None:
        """Insert the plan of a request; ``None`` when a plan is open already (the one-open-plan index)."""
        open_states = (PlanState.BUILDING, PlanState.READY, PlanState.SCHEDULED, PlanState.APPLYING)
        if any(p.state in open_states for p in self.plans) or any(s in open_states for s in self.auto_state.values()):
            return None
        plan = PlanRecord(
            uuid.uuid4(), list_version, PlanState.BUILDING, None, 0, 0, 0, cap, request.request_id, request.threshold
        )
        self.plans.append(plan)
        self.items[plan.plan_id] = []
        self.auto[plan.plan_id] = []
        self.auto_state[plan.plan_id] = PlanState.BUILDING
        self.planned.add(request.request_id)
        return plan

    def _set(self, plan_id: uuid.UUID, **changes: object) -> PlanRecord:
        index = next(i for i, p in enumerate(self.plans) if p.plan_id == plan_id)
        self.plans[index] = replace(self.plans[index], **changes)  # type: ignore[arg-type]
        return self.plans[index]

    async def replace_plan(self, plan_id: uuid.UUID) -> bool:
        plan = next(p for p in self.plans if p.plan_id == plan_id)
        if plan.state not in (PlanState.BUILDING, PlanState.READY):
            return False
        self._set(plan_id, state=PlanState.REPLACED)
        self.items[plan_id] = []
        if self.auto_state.get(plan_id) is PlanState.BUILDING:
            self.auto_state[plan_id] = PlanState.REPLACED
            self.auto[plan_id] = []
        return True

    async def record_estimate(self, plan_id: uuid.UUID, estimate: int) -> None:
        self.estimates[plan_id] = estimate

    async def complete_build(self, plan_id: uuid.UUID, *, not_looked_at: int) -> bool:
        plan = next(p for p in self.plans if p.plan_id == plan_id)
        if plan.state is not PlanState.BUILDING:
            return False
        self._set(plan_id, state=PlanState.READY)
        self.not_looked_at[plan_id] = not_looked_at
        if self.auto_state.get(plan_id) is PlanState.BUILDING:  # the database approves the auto plan in this step
            self.auto_state[plan_id] = PlanState.SCHEDULED if self.auto[plan_id] else PlanState.REPLACED
        return True

    async def rejected_ids(self, list_version: int) -> frozenset[str]:
        return frozenset(m for m, v in self.rejections.items() if v == list_version)

    async def record_progress(  # noqa: PLR0913
        self, plan_id: uuid.UUID, *, item: ItemDraft | None, kind: PlanKind, cursor: str, checked: int, unclear: int
    ) -> bool:
        plan = next(p for p in self.plans if p.plan_id == plan_id)
        if plan.state is not PlanState.BUILDING:
            return False
        review = item is not None and kind is PlanKind.REVIEW
        auto = item is not None and kind is PlanKind.AUTO
        if item is not None:
            (self.items if review else self.auto)[plan_id].append(item)
        self._set(
            plan_id,
            cursor=cursor,
            checked=plan.checked + checked,
            unclear=plan.unclear + unclear,
            items=plan.items + review,
            auto_items=plan.auto_items + auto,
        )
        return True


class GmailBuildMailbox:
    """The mailbox port on the Gmail double: listing is what the real query returns (inbox or a list label)."""

    def __init__(self, gmail: FakeGmail) -> None:
        self.gmail = gmail
        self.ghosts: list[str] = []  # listed, then deleted before they are read
        self.listed_names: set[str] = {"Finance", "Travel", "Newsletter", "Receipt", OTHER_NAME}

    def label_names(self) -> dict[str, str]:
        return dict(self.gmail.label_table)

    def _listed(self) -> list[str]:
        names = self.gmail.label_table
        ids = [
            m.mid
            for m in reversed(self.gmail.mail_table.values())
            if not {"SPAM", "TRASH"} & m.labels
            and ("INBOX" in m.labels or any(names[i] in self.listed_names for i in m.labels))
        ]
        return [*self.ghosts, *ids]

    def estimate_in_scope(self) -> int:
        return len(self._listed())

    def candidates(self, after: str | None, limit: int) -> list[Candidate]:
        ids = self._listed()
        start = ids.index(after) + 1 if after is not None else 0
        return [Candidate(i, i) for i in ids[start : start + limit]]

    def fetch(self, message_id: str) -> FetchedMail | None:
        mail = self.gmail.mail_table.get(message_id)
        if mail is None:
            return None
        return FetchedMail(
            message_id=mail.mid,
            thread_id=f"t-{mail.mid}",
            sender=mail.headers["From"],
            reply_to=None,
            subject=mail.headers["Subject"],
            text=mail.text,
            has_attachment=False,
            headers=dict(mail.headers),
            labels=frozenset(mail.labels),
            auth_results=(mail.headers["Authentication-Results"],) if "Authentication-Results" in mail.headers else (),
        )


@dataclass
class ScriptedJudge:
    """Answers with ``answer`` (a topic id) for every mail, or per subject; spends ``cost`` from the ledger.

    ``answers`` gives (topic, extra, confidence) per subject; ``raw`` gives a raw model answer per subject that goes
    through the same validation as the real one.
    """

    answer: str = FINANCE
    by_subject: dict[str, str] = field(default_factory=dict)
    answers: dict[str, tuple[str, str | None, float]] = field(default_factory=dict)
    raw: dict[str, dict[str, object]] = field(default_factory=dict)
    ledger: BudgetLedger | None = None
    cost: int = 2
    on_judge: Callable[[], None] | None = None
    verdict: NeedsAttention | None = None
    calls: int = 0
    subjects: list[str] = field(default_factory=list)

    async def judge(
        self, mail: TrimmedMail, categories: Sequence[ListedCategory], instructions: str
    ) -> Judgement | NeedsAttention:
        self.calls += 1
        self.subjects.append(mail.subject)
        if self.ledger is not None:
            self.ledger.spend(self.cost)
        if self.on_judge is not None:
            self.on_judge()
        if self.verdict is not None:
            return self.verdict
        if mail.subject in self.raw:
            try:
                return parse_judgement(self.raw[mail.subject])
            except JudgementError:
                return NeedsAttention("invalid_output")
        topic, extra, confidence = self.answers.get(
            mail.subject, (self.by_subject.get(mail.subject, self.answer), None, 0.9)
        )
        return Judgement(topic_id=topic, extra_id=extra, urgent=False, reason="r", summary="s", confidence=confidence)


class FakeTips:
    """The tip writer: records the plan and the list it was asked for."""

    def __init__(self, telegram: FakeTelegram) -> None:
        self._telegram = telegram
        self.calls: list[tuple[uuid.UUID, tuple[str, ...]]] = []
        self.seen_texts: list[int] = []  # how many notices were out when each write started

    async def write(self, plan_id: uuid.UUID, categories: Sequence[ListedCategory]) -> int:
        self.seen_texts.append(len(self._telegram.texts))
        self.calls.append((plan_id, tuple(c.category_id for c in categories)))
        return 0


class Rig:
    """Everything a build test needs, wired the way the agent will wire it."""

    def __init__(self, *, daily_total: int = DAILY_TOTAL, per_run: int = 100_000) -> None:
        """``per_run`` is large unless a test is about the slices of one run."""
        self.clock = FakeClock(START)
        self.gmail = FakeGmail()
        self.mailbox = GmailBuildMailbox(self.gmail)
        self.store = FakeBuildStore(self.clock, self.gmail)
        self.ledger = BudgetLedger(self.clock, daily_total=daily_total, reserve=RESERVE)
        self.judge = ScriptedJudge(ledger=self.ledger)
        self.telegram = FakeTelegram()
        self.tips = FakeTips(self.telegram)
        self.finance_label = self.gmail.add_label("Finance")
        self.travel_label = self.gmail.add_label("Travel")
        self.build = ResortBuild(
            mailbox=self.mailbox,
            judge=self.judge,
            store=self.store,
            notifier=self.telegram,
            tips=self.tips,
            budget=self,
            now=self.clock,
            pinned=PINNED,
            per_run=per_run,
        )

    def request(self, threshold: int = 50) -> ResortRequest:
        """The user presses "Sort everything again"; the next run starts the plan."""
        return self.store.add_request(threshold)

    def remaining(self) -> int:
        """The budget view the use case reads: what the day still allows, the reserve included."""
        return self.ledger.available() + RESERVE


__all__ = ["ARCHIVE_NAME", "CATEGORIES", "FINANCE", "OTHER_ID", "PINNED", "RESERVE", "START", "TRAVEL", "Rig"]
