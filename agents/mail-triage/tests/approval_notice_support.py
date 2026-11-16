"""Test doubles for the approval notice: plan store with the compare-and-set of the database, move back requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.adapters.telegram_inbox import Command
from app.core import approval_text
from app.usecases.approval_notice import (
    ApprovalNotice,
    CancelOutcome,
    PlanNoticeActions,
    ScheduledPlan,
)
from app.usecases.telegram_actions import TelegramActions
from tests.list_notice_support import CHAT, FakeActionStore, FakeLock, Nonces, RecordingChat

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
DELAY = timedelta(minutes=15)
PLAN = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_PLAN = uuid.UUID("22222222-2222-2222-2222-222222222222")


@dataclass
class FakePlanStore:
    """Plan states, as the database keeps them; Cancel is one compare-and-set."""

    states: dict[uuid.UUID, str] = field(default_factory=dict)
    after: dict[uuid.UUID, datetime] = field(default_factory=dict)
    counts: dict[uuid.UUID, int] = field(default_factory=dict)
    announced: set[uuid.UUID] = field(default_factory=set)
    clock: list[datetime] = field(default_factory=lambda: [NOW])  # the database clock

    def schedule(self, plan: uuid.UUID = PLAN, count: int = 60, at: datetime = NOW + DELAY) -> None:
        self.states[plan], self.after[plan], self.counts[plan] = "scheduled", at, count

    async def unannounced(self) -> list[ScheduledPlan]:
        return [
            ScheduledPlan(p, self.counts[p], self.after[p])
            for p, s in self.states.items()
            if s == "scheduled" and p not in self.announced
        ]

    async def mark_announced(self, plan_id: uuid.UUID) -> None:
        self.announced.add(plan_id)

    async def cancel_before_start(self, plan_id: uuid.UUID) -> CancelOutcome:
        if self.states.get(plan_id) != "scheduled":
            return CancelOutcome.NOT_SCHEDULED
        if self.clock[0] >= self.after[plan_id]:
            return CancelOutcome.TOO_LATE
        self.states[plan_id] = "cancelled"
        return CancelOutcome.CANCELLED

    async def cancel_open_plans(self) -> int:
        open_plans = [p for p, s in self.states.items() if s in {"scheduled", "applying"}]
        for plan in open_plans:
            self.states[plan] = "cancelled"
        return len(open_plans)


@dataclass
class FakeMoveBack:
    """``move_back_request``: one request per applied plan."""

    applied: set[uuid.UUID] = field(default_factory=set)
    requested: list[uuid.UUID] = field(default_factory=list)

    async def request(self, plan_id: uuid.UUID) -> bool:
        if plan_id not in self.applied or plan_id in self.requested:
            return False
        self.requested.append(plan_id)
        return True


class Rig:
    """The notice and its button handler on shared fakes."""

    def __init__(self) -> None:
        self.clock = [NOW]
        self.plans, self.chat, self.lock = FakePlanStore(clock=self.clock), RecordingChat(), FakeLock()
        self.back = FakeMoveBack()
        actions = TelegramActions(FakeActionStore(), Nonces())
        self.notice = ApprovalNotice(actions, self.plans, self.chat, chat_id=CHAT)
        self.buttons = PlanNoticeActions(
            actions, self.plans, self.back, self.lock, self.chat, chat_id=CHAT, now=lambda: self.clock[0]
        )

    def data(self, index: int, message: int = 0) -> str:
        return self.chat.sent[message].buttons[index].data

    async def press(self, data: str, *, chat_id: int = CHAT, message_id: int = 7) -> None:
        split = approval_text.split_button(data)
        assert split is not None
        await self.buttons.on_button(Command("button", data, chat_id, message_id, "cb", 1), *split)


def scheduled() -> Rig:
    rig = Rig()
    rig.plans.schedule()
    return rig
