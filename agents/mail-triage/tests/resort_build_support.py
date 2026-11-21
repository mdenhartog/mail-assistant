"""Doubles for the plan build tests: an in-memory plan store, a Gmail-backed mailbox view, a scripted judge."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.adapters.gmail_read import FetchedMail
from app.core.judgement import OTHER_ID, Judgement, ListedCategory, NeedsAttention
from app.core.pinned import PinnedSenders
from app.core.resort_plan import PlanState
from app.usecases.resort_build import BuildList, Candidate, ItemDraft, PlanRecord, ResortBuild
from tests.fakes.budget_ledger import BudgetLedger
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.fake_telegram import FakeTelegram

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from app.adapters.judge_anthropic import TrimmedMail

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


class FakeBuildStore:
    """The plan tables in memory. A plan that is not ``building`` refuses progress, like the compare-and-set."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.list = BuildList(version=1, changed_at=clock(), categories=CATEGORIES)
        self.plans: list[PlanRecord] = []
        self.items: dict[uuid.UUID, list[ItemDraft]] = {}
        self.rejections: dict[str, int] = {}  # message id -> list version
        self.estimates: dict[uuid.UUID, int] = {}
        self.not_looked_at: dict[uuid.UUID, int] = {}

    def save_list(self, categories: Sequence[ListedCategory] = CATEGORIES) -> None:
        """The user saves a new list version now."""
        self.list = BuildList(self.list.version + 1, self._clock(), tuple(categories))

    def reject(self, message_id: str, version: int | None = None) -> None:
        self.rejections[message_id] = self.list.version if version is None else version

    def plan(self, index: int = -1) -> PlanRecord:
        return self.plans[index]

    def items_of(self, plan: PlanRecord) -> list[ItemDraft]:
        return self.items.get(plan.plan_id, [])

    async def current_list(self) -> BuildList:
        return self.list

    async def latest_plan(self) -> PlanRecord | None:
        return self.plans[-1] if self.plans else None

    async def create_plan(self, list_version: int, cap: int) -> PlanRecord | None:
        if any(p.state in (PlanState.BUILDING, PlanState.READY) for p in self.plans):
            return None
        plan = PlanRecord(uuid.uuid4(), list_version, PlanState.BUILDING, None, 0, 0, 0, cap)
        self.plans.append(plan)
        self.items[plan.plan_id] = []
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
        return True

    async def record_estimate(self, plan_id: uuid.UUID, estimate: int) -> None:
        self.estimates[plan_id] = estimate

    async def complete_build(self, plan_id: uuid.UUID, *, not_looked_at: int) -> bool:
        plan = next(p for p in self.plans if p.plan_id == plan_id)
        if plan.state is not PlanState.BUILDING:
            return False
        self._set(plan_id, state=PlanState.READY)
        self.not_looked_at[plan_id] = not_looked_at
        return True

    async def rejected_ids(self, list_version: int) -> frozenset[str]:
        return frozenset(m for m, v in self.rejections.items() if v == list_version)

    async def record_progress(
        self, plan_id: uuid.UUID, *, item: ItemDraft | None, cursor: str, checked: int, unclear: int
    ) -> bool:
        plan = next(p for p in self.plans if p.plan_id == plan_id)
        if plan.state is not PlanState.BUILDING:
            return False
        if item is not None:
            self.items[plan_id].append(item)
        self._set(
            plan_id,
            cursor=cursor,
            checked=plan.checked + checked,
            unclear=plan.unclear + unclear,
            items=plan.items + (item is not None),
        )
        return True


class GmailBuildMailbox:
    """The mailbox port on the Gmail double: listing is what the real query returns (inbox or ``Assistant/`` label)."""

    def __init__(self, gmail: FakeGmail) -> None:
        self.gmail = gmail
        self.ghosts: list[str] = []  # listed, then deleted before they are read

    def label_names(self) -> dict[str, str]:
        return dict(self.gmail.label_table)

    def _listed(self) -> list[str]:
        names = self.gmail.label_table
        ids = [
            m.mid
            for m in reversed(self.gmail.mail_table.values())
            if not {"SPAM", "TRASH"} & m.labels
            and ("INBOX" in m.labels or any(names[i].startswith("Assistant/") for i in m.labels))
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
    """Answers with ``answer`` (a category id) for every mail, or per subject; spends ``cost`` from the ledger."""

    answer: str = FINANCE
    by_subject: dict[str, str] = field(default_factory=dict)
    ledger: BudgetLedger | None = None
    cost: int = 2
    on_judge: Callable[[], None] | None = None
    verdict: NeedsAttention | None = None
    calls: int = 0

    async def judge(self, mail: TrimmedMail, categories: Sequence[ListedCategory]) -> Judgement | NeedsAttention:
        self.calls += 1
        if self.ledger is not None:
            self.ledger.spend(self.cost)
        if self.on_judge is not None:
            self.on_judge()
        if self.verdict is not None:
            return self.verdict
        category_id = self.by_subject.get(mail.subject, self.answer)
        return Judgement(category_id=category_id, urgent=False, reason="r", summary="s", confidence=0.9)


class Rig:
    """Everything a build test needs, wired the way the agent will wire it."""

    def __init__(self, *, daily_total: int = DAILY_TOTAL, per_run: int = 100_000) -> None:
        """``per_run`` is large unless a test is about the slices of one run."""
        self.clock = FakeClock(START)
        self.gmail = FakeGmail()
        self.mailbox = GmailBuildMailbox(self.gmail)
        self.store = FakeBuildStore(self.clock)
        self.ledger = BudgetLedger(self.clock, daily_total=daily_total, reserve=RESERVE)
        self.judge = ScriptedJudge(ledger=self.ledger)
        self.telegram = FakeTelegram()
        self.finance_label = self.gmail.add_label("Assistant/Finance")
        self.travel_label = self.gmail.add_label("Assistant/Travel")
        self.build = ResortBuild(
            mailbox=self.mailbox,
            judge=self.judge,
            store=self.store,
            notifier=self.telegram,
            budget=self,
            now=self.clock,
            pinned=PINNED,
            archive_label="Archive",
            debounce=timedelta(minutes=10),
            per_run=per_run,
        )

    def remaining(self) -> int:
        """The budget view the use case reads: what the day still allows, the reserve included."""
        return self.ledger.available() + RESERVE


__all__ = ["CATEGORIES", "FINANCE", "OTHER_ID", "PINNED", "RESERVE", "START", "TRAVEL", "Rig"]
