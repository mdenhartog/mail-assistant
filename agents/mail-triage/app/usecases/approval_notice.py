"""Telegram side of a delayed apply: the notice, Cancel, Lock and Move back (spec D16, D17, AC-42, AC-48, AC-57).

See ADR-0046 and ADR-0033.

An approval above the threshold makes a ``scheduled`` plan that the agent applies after ``apply_after``. Each run
sends one notice per such plan (then marks it announced; a failed send is repeated with new nonces). Cancel and Lock
carry single-use nonces whose target is the plan id. Cancel is one compare-and-set in the store: it wins only while
the plan is still ``scheduled`` and the database clock is before ``apply_after``, so a Cancel after the delay is
refused and says so. Lock sets the web lock first and then cancels every ``scheduled`` or ``applying`` plan (the apply
also stops before its next batch on the lock). Move back asks for the restore of an applied plan, once per plan. The
result notice (counts) is sent by the notifier through ``send_result``. Buttons from another chat, used, late or of
another kind change nothing. Nothing here reads the clock or makes a random value, and nothing logs.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from app.core import approval_text
from app.core.alert_text import AlertMessage, Button
from app.usecases.resort_apply import Offer
from app.usecases.telegram_actions import Refusal

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from app.adapters.telegram_inbox import Command
    from app.usecases.list_notice import NoticeChat, WebLock
    from app.usecases.telegram_actions import TelegramActions

__all__ = [
    "ApprovalNotice",
    "ApprovalStore",
    "CancelOutcome",
    "MoveBackRequests",
    "PlanNoticeActions",
    "ScheduledPlan",
]

_KINDS: Final = {
    approval_text.CANCEL: "plan_cancel",
    approval_text.LOCK: "plan_lock",
    approval_text.MOVE_BACK: "plan_move_back",
}
_LABELS: Final = {
    approval_text.CANCEL: approval_text.CANCEL_LABEL,
    approval_text.LOCK: approval_text.LOCK_LABEL,
    approval_text.MOVE_BACK: approval_text.MOVE_BACK_LABEL,
}
_REFUSALS: Final = {
    Refusal.DONE: approval_text.ALREADY_DONE,
    Refusal.EXPIRED: approval_text.EXPIRED,
    Refusal.OTHER_CHAT: approval_text.OTHER_CHAT,
}


@dataclass(frozen=True, slots=True)
class ScheduledPlan:
    """A ``scheduled`` plan: how many mails it moves and when the apply may start."""

    plan_id: uuid.UUID
    mail_count: int
    apply_after: datetime


class CancelOutcome(enum.Enum):
    """What a Cancel did."""

    CANCELLED = "cancelled"
    TOO_LATE = "too_late"  # scheduled, but ``apply_after`` has been reached
    NOT_SCHEDULED = "not_scheduled"  # cancelled, applying, applied or gone already


class ApprovalStore(Protocol):
    """The plans as the notice and its buttons need them; every state change is a compare-and-set."""

    async def unannounced(self) -> list[ScheduledPlan]:
        """``scheduled`` plans without a notice yet."""
        ...

    async def mark_announced(self, plan_id: uuid.UUID) -> None:
        """Remember that the notice of the plan was sent."""
        ...

    async def cancel_before_start(self, plan_id: uuid.UUID) -> CancelOutcome:
        """``scheduled`` to ``cancelled`` while the database clock is before ``apply_after``, in one statement."""
        ...

    async def cancel_open_plans(self) -> int:
        """Every ``scheduled`` or ``applying`` plan of the mailbox to ``cancelled``; return how many."""
        ...


class MoveBackRequests(Protocol):
    """``move_back_request``."""

    async def request(self, plan_id: uuid.UUID) -> bool:
        """Ask for the restore of an ``applied`` plan; ``False`` when it is not applied or was asked already."""
        ...


class ApprovalNotice:
    """Announces scheduled plans and sends the result notice with its buttons."""

    def __init__(self, actions: TelegramActions, store: ApprovalStore, chat: NoticeChat, *, chat_id: int) -> None:
        """Wire the button nonces, the plans, Telegram and the one allowed chat."""
        self._actions = actions
        self._store = store
        self._chat = chat
        self._chat_id = chat_id

    async def run(self, now: datetime) -> None:
        """Send one notice for each scheduled plan not announced yet."""
        for plan in await self._store.unannounced():
            cancel = await self._button(approval_text.CANCEL, plan.plan_id, now)
            lock = await self._button(approval_text.LOCK, plan.plan_id, now)
            await self._chat.send(
                approval_text.scheduled_notice(
                    plan.mail_count, plan.apply_after, now=now, cancel_data=cancel.data, lock_data=lock.data
                )
            )
            await self._store.mark_announced(plan.plan_id)

    async def send_result(self, text: str, plan_id: uuid.UUID, offers: tuple[Offer, ...], now: datetime) -> int:
        """Send the result ``text`` with a Move back and/or Lock button, each with its own nonce."""
        buttons = [
            await self._button(
                approval_text.MOVE_BACK if offer is Offer.MOVE_BACK else approval_text.LOCK, plan_id, now
            )
            for offer in offers
        ]
        return await self._chat.send(AlertMessage(text, tuple(buttons)))

    async def _button(self, action: str, plan_id: uuid.UUID, now: datetime) -> Button:
        nonce = await self._actions.issue(_KINDS[action], str(plan_id), self._chat_id, now)
        return Button(_LABELS[action], approval_text.button_data(action, nonce))


class PlanNoticeActions:
    """Handles ``plancancel``, ``planlock`` and ``planback``."""

    def __init__(  # noqa: PLR0913 - every dependency is injected for tests
        self,
        actions: TelegramActions,
        store: ApprovalStore,
        move_back: MoveBackRequests,
        lock: WebLock,
        chat: NoticeChat,
        *,
        chat_id: int,
        now: Callable[[], datetime],
    ) -> None:
        """Wire the nonces, the plans, the move back requests, the web lock, Telegram, the one chat and the clock."""
        self._actions = actions
        self._store = store
        self._move_back = move_back
        self._lock = lock
        self._chat = chat
        self._chat_id = chat_id
        self._now = now

    async def on_button(self, command: Command, action: str, nonce: str) -> None:
        """Run one plan button; the answer replaces the notice, which drops its buttons."""
        kind = _KINDS.get(action)
        if kind is None:
            return
        if command.chat_id != self._chat_id:  # never edit by message id for a chat that is not ours
            await self._chat.say(approval_text.OTHER_CHAT)
            return
        now = self._now()
        outcome = await self._actions.redeem(nonce, kind, command.chat_id, now)
        if isinstance(outcome, Refusal):
            await self._chat.edit_message(command.message_id, _REFUSALS[outcome])
            return
        plan_id = uuid.UUID(outcome.target)
        if action == approval_text.CANCEL:
            answer = await self._cancel(plan_id)
        elif action == approval_text.LOCK:
            answer = await self._lock_all(now)
        else:
            asked = await self._move_back.request(plan_id)
            answer = approval_text.MOVE_BACK_ASKED if asked else approval_text.MOVE_BACK_UNAVAILABLE
        await self._chat.edit_message(command.message_id, answer)

    async def _cancel(self, plan_id: uuid.UUID) -> str:
        result = await self._store.cancel_before_start(plan_id)
        return {
            CancelOutcome.CANCELLED: approval_text.CANCELLED,
            CancelOutcome.TOO_LATE: approval_text.TOO_LATE,
            CancelOutcome.NOT_SCHEDULED: approval_text.NOT_WAITING,
        }[result]

    async def _lock_all(self, now: datetime) -> str:
        await self._lock.lock(now)  # first: the lock must hold whatever the cancel finds
        return approval_text.locked_and_cancelled(await self._store.cancel_open_plans())
