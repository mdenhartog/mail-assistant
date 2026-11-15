"""Doubles for the apply and move-back tests: an in-memory store, Gmail through the real narrow adapter, a lock."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from googleapiclient.errors import HttpError

from app.adapters.gmail_resort import GmailResort
from app.core.judgement import OTHER_ID
from app.core.resort_plan import ItemState, PlanState
from app.usecases.move_back import MoveBack, MoveBackJob
from app.usecases.resort_apply import (
    ApplyItem,
    AuditMove,
    DuePlan,
    MailFailed,
    MailGone,
    Offer,
    ResortApply,
    SkipReason,
)
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.fake_telegram import FakeTelegram
from tests.resort_build_support import CATEGORIES, FINANCE, PINNED, START, TRAVEL, GmailBuildMailbox

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.gmail_read import FetchedMail

LEASE = timedelta(minutes=5)
GOOGLE_AUTH = "mx.google.com; dmarc=pass header.from=accounts.google.com"


@dataclass
class ItemRow:
    """One plan item as the store keeps it."""

    item: ApplyItem
    state: ItemState = ItemState.APPROVED
    reason: SkipReason | None = None


@dataclass
class PlanRow:
    """One plan as the store keeps it."""

    due: DuePlan
    lease_owner: str | None = None
    lease_until: datetime | None = None
    items: list[ItemRow] = field(default_factory=list)


class FakeApplyStore:
    """Plan, items, audit and move-back requests in memory, with the compare-and-set rules of the real tables."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.categories: dict[str, str] = {c.category_id: c.name for c in CATEGORIES}
        self.plans: dict[uuid.UUID, PlanRow] = {}
        self.intents: dict[tuple[uuid.UUID, str], AuditMove] = {}
        self.restores: list[tuple[uuid.UUID, AuditMove, str]] = []
        self.requests: dict[uuid.UUID, MoveBackJob] = {}
        self.processed: set[uuid.UUID] = set()
        self.request_lease: dict[uuid.UUID, tuple[str, datetime]] = {}
        self.fail_finish_item_once = False
        self.attempts: dict[tuple[uuid.UUID, str], int] = {}

    def add_plan(
        self, items: list[ApplyItem], *, apply_after: timedelta = timedelta(0), state: PlanState = PlanState.SCHEDULED
    ) -> uuid.UUID:
        plan_id = uuid.uuid4()
        due = DuePlan(plan_id, state, self._clock() + apply_after, "web", "a" * 64)
        self.plans[plan_id] = PlanRow(due, items=[ItemRow(i) for i in items])
        return plan_id

    def state(self, plan_id: uuid.UUID) -> PlanState:
        return self.plans[plan_id].due.state

    def item(self, plan_id: uuid.UUID, message_id: str) -> ItemRow:
        return next(r for r in self.plans[plan_id].items if r.item.message_id == message_id)

    def _set_state(self, plan_id: uuid.UUID, state: PlanState) -> None:
        row = self.plans[plan_id]
        row.due = replace(row.due, state=state)

    # --- ApplyStore -----------------------------------------------------------------------------------------------

    async def plans_to_apply(self) -> list[DuePlan]:
        return [p.due for p in self.plans.values() if p.due.state in (PlanState.SCHEDULED, PlanState.APPLYING)]

    async def claim(self, plan_id: uuid.UUID, run_id: str) -> bool:
        row = self.plans[plan_id]
        now = self._clock()
        free = row.lease_until is None or row.lease_until <= now
        if row.due.state is PlanState.SCHEDULED or (row.due.state is PlanState.APPLYING and free):
            self._set_state(plan_id, PlanState.APPLYING)
            row.lease_owner, row.lease_until = run_id, now + LEASE
            return True
        return False

    async def begin_batch(self, plan_id: uuid.UUID, run_id: str) -> bool:
        row = self.plans[plan_id]
        if row.due.state is not PlanState.APPLYING or row.lease_owner != run_id:
            return False
        row.lease_until = self._clock() + LEASE
        return True

    async def cancel(self, plan_id: uuid.UUID) -> bool:
        if self.state(plan_id) not in (PlanState.SCHEDULED, PlanState.APPLYING):
            return False
        self._set_state(plan_id, PlanState.CANCELLED)
        return True

    async def current_categories(self) -> dict[str, str]:
        return dict(self.categories)

    async def next_items(self, plan_id: uuid.UUID, limit: int) -> list[ApplyItem]:
        rows = [r.item for r in self.plans[plan_id].items if r.state is ItemState.APPROVED]
        return rows[:limit]

    async def intent_for(self, plan_id: uuid.UUID, message_id: str) -> AuditMove | None:
        return self.intents.get((plan_id, message_id))

    async def record_intent(self, plan_id: uuid.UUID, move: AuditMove) -> None:
        self.intents.setdefault((plan_id, move.message_id), move)

    async def count_attempt(self, plan_id: uuid.UUID, message_id: str) -> int:
        key = (plan_id, message_id)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return self.attempts[key]

    async def finish_item(
        self, plan_id: uuid.UUID, message_id: str, state: ItemState, reason: SkipReason | None
    ) -> bool:
        if self.fail_finish_item_once and state is ItemState.APPLIED:
            self.fail_finish_item_once = False
            raise ConnectionError("the database write failed")
        row = self.item(plan_id, message_id)
        if row.state is not ItemState.APPROVED:
            return False
        row.state, row.reason = state, reason
        return True

    async def finish_plan(self, plan_id: uuid.UUID, run_id: str) -> bool:
        row = self.plans[plan_id]
        if row.due.state is not PlanState.APPLYING or row.lease_owner != run_id:
            return False
        self._set_state(plan_id, PlanState.APPLIED)
        return True

    async def item_counts(self, plan_id: uuid.UUID) -> dict[ItemState, int]:
        counts: dict[ItemState, int] = {}
        for row in self.plans[plan_id].items:
            counts[row.state] = counts.get(row.state, 0) + 1
        return counts

    async def remove_applied_items(self, plan_id: uuid.UUID) -> None:
        row = self.plans[plan_id]
        row.items = [r for r in row.items if r.state is not ItemState.APPLIED]

    async def audit_moves(self, plan_id: uuid.UUID) -> list[AuditMove]:
        return [m for (p, _), m in self.intents.items() if p == plan_id]

    # --- MoveBackStore --------------------------------------------------------------------------------------------

    def request_move_back(self, plan_id: uuid.UUID, channel: str = "web") -> None:
        self.requests[plan_id] = MoveBackJob(plan_id, self.state(plan_id), channel, "b" * 64)

    async def pending_requests(self) -> list[MoveBackJob]:
        return [j for p, j in self.requests.items() if p not in self.processed]

    async def claim_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        held = self.request_lease.get(plan_id)
        now = self._clock()
        if plan_id in self.processed or (held is not None and held[1] > now):
            return False
        self.request_lease[plan_id] = (run_id, now + LEASE)
        return True

    async def renew_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        held = self.request_lease.get(plan_id)
        if plan_id in self.processed or held is None or held[0] != run_id:
            return False
        self.request_lease[plan_id] = (run_id, self._clock() + LEASE)
        return True

    async def record_restore(self, plan_id: uuid.UUID, move: AuditMove, channel: str) -> None:
        self.restores.append((plan_id, move, channel))

    async def finish_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        held = self.request_lease.get(plan_id)
        if plan_id in self.processed or held is None or held[0] != run_id:
            return False
        self.processed.add(plan_id)
        return True


class GmailApplyMailbox(GmailBuildMailbox):
    """Reads like the build mailbox; writes only through the real narrow adapter ``GmailResort``."""

    def __init__(self, gmail: FakeGmail) -> None:
        super().__init__(gmail)
        self.resort = GmailResort(gmail, sleep=lambda _seconds: None)
        self.on_add: Callable[[str], None] | None = None
        self.on_remove: Callable[[str], None] | None = None
        self.failing_adds: dict[str, int] = {}  # message id -> failures left (-1: always), as Gmail refusing the change
        self.failing_fetches: set[str] = set()

    def fetch_labels(self, message_id: str) -> FetchedMail | None:
        return self.fetch(message_id)

    def fetch(self, message_id: str) -> FetchedMail | None:
        if message_id in self.failing_fetches:
            raise MailFailed
        return super().fetch(message_id)

    def ensure_label(self, name: str) -> str:
        return self.resort.create_label(name).id

    def add_label(self, message_id: str, label_id: str) -> None:
        left = self.failing_adds.get(message_id, 0)
        if left:
            self.failing_adds[message_id] = max(left - 1, -1) if left > 0 else -1
            raise MailFailed
        self._guard(lambda: self.resort.add_label(message_id, label_id))
        if self.on_add is not None:
            self.on_add(message_id)

    def remove_label(self, message_id: str, label_id: str) -> None:
        if self.on_remove is not None:
            self.on_remove(message_id)
        self._guard(lambda: self.resort.remove_label(message_id, label_id))

    def count_mail(self, label_id: str) -> int:
        return self.resort.count_mail(label_id)

    @staticmethod
    def _guard(call: Callable[[], None]) -> None:
        try:
            call()
        except HttpError as error:
            if error.resp.status == 404:
                raise MailGone from error
            raise MailFailed from error


class FakeLock:
    """The web lock; ``locked_after`` sets it once that many checks have been made."""

    def __init__(self) -> None:
        self.locked = False
        self.locked_after: int | None = None
        self.checks = 0

    async def is_locked(self) -> bool:
        self.checks += 1
        if self.locked_after is not None and self.checks > self.locked_after:
            self.locked = True
        return self.locked


class FakeNotifier:
    """Records result notices with their offers, and plain notes."""

    def __init__(self, telegram: FakeTelegram) -> None:
        self.telegram = telegram
        self.results: list[tuple[uuid.UUID, tuple[Offer, ...]]] = []

    async def say(self, text: str) -> None:
        await self.telegram.say(text)

    async def result(self, text: str, *, plan_id: uuid.UUID, offers: tuple[Offer, ...]) -> None:
        await self.telegram.say(text)
        self.results.append((plan_id, offers))


class ApplyRig:
    """Gmail, the stores and the two use cases wired together."""

    def __init__(self, *, batch_size: int = 50) -> None:
        self.clock = FakeClock(START)
        self.gmail = FakeGmail()
        self.finance = self.gmail.add_label("Assistant/Finance")
        self.travel = self.gmail.add_label("Assistant/Travel")
        self.mailbox = GmailApplyMailbox(self.gmail)
        self.store = FakeApplyStore(self.clock)
        self.lock = FakeLock()
        self.telegram = FakeTelegram()
        self.notifier = FakeNotifier(self.telegram)
        self.batch_size = batch_size

    def apply(self) -> ResortApply:
        return ResortApply(
            mailbox=self.mailbox,
            store=self.store,
            lock=self.lock,
            notifier=self.notifier,
            now=self.clock,
            pinned=PINNED,
            batch_size=self.batch_size,
        )

    def move_back(self) -> MoveBack:
        return MoveBack(
            mailbox=self.mailbox, store=self.store, lock=self.lock, notifier=self.notifier, batch_size=self.batch_size
        )

    def mail(self, labels: tuple[str, ...] = ("INBOX",), **kw: str) -> str:
        return self.gmail.add_mail(labels, **kw)

    def labels_of(self, mid: str) -> set[str]:
        names = self.gmail.label_table
        return {names[i] for i in self.gmail.mail_table[mid].labels}

    def modifies(self) -> int:
        return self.gmail.calls.count("messages.modify")


def item(mid: str, old: str, new: str) -> ApplyItem:
    return ApplyItem(mid, uuid.UUID(old), uuid.UUID(new))


__all__ = ["FINANCE", "GOOGLE_AUTH", "OTHER_ID", "TRAVEL", "UTC", "ApplyRig", "item"]
