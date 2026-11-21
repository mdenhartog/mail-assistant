"""Move back an applied plan: restore the old labels from the apply audit (INT-004).

ADR-0046 point 5, spec AC-41, AC-57, AC-26 (the one exception: old labels come back even when their category left
the list).

Only an ``applied`` plan with an open request is processed, once: one run holds a lease on the request, and the one
compare-and-set that closes it decides who sends the single Telegram notice. A mail is restored only when it still
looks the way the apply left it (in scope and carrying the new label and no other ``Assistant/`` label); anything else
was changed meanwhile and is skipped. Like the apply, the swap adds the old label first and removes the new one second,
so a crash between the two leaves both labels and a retry finishes it. The web lock stops it before the next batch.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.core.resort_plan import PlanState
from app.core.scope import Scope, classify
from app.usecases.resort_apply import AuditMove, MailFailed, MailGone, held_label_ids

if TYPE_CHECKING:
    from app.usecases.resort_apply import ApplyLock, ApplyMailbox, ApplyNotifier

__all__ = ["BATCH_SIZE", "MoveBack", "MoveBackJob", "MoveBackStore"]

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


@dataclass(frozen=True, slots=True)
class MoveBackJob:
    """An open request: the plan, its state, and the channel and actor digest of whoever asked."""

    plan_id: uuid.UUID
    plan_state: PlanState
    channel: str
    actor_digest: str


class MoveBackStore(Protocol):
    """``move_back_request`` and ``apply_audit`` as the move back needs them."""

    async def pending_requests(self) -> list[MoveBackJob]:
        """Requests not yet processed."""
        ...

    async def claim_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """Take the request when it is open and no other run holds its lease; one caller wins."""
        ...

    async def renew_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """True while this run holds the lease of an open request; renews the lease."""
        ...

    async def audit_moves(self, plan_id: uuid.UUID) -> list[AuditMove]:
        """The apply rows of the plan (not rows written by a move back)."""
        ...

    async def record_restore(self, plan_id: uuid.UUID, move: AuditMove, channel: str) -> None:
        """Insert an audit row for a restore (old and new swapped) with the channel and actor of the request."""
        ...

    async def finish_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """Compare-and-set the request to processed for the lease holder; true for exactly one caller."""
        ...


class MoveBack:
    """Restores the labels of applied plans on request."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        mailbox: ApplyMailbox,
        store: MoveBackStore,
        lock: ApplyLock,
        notifier: ApplyNotifier,
        archive_label: str,  # the protected label (C-14, ADR-0052)
        batch_size: int = BATCH_SIZE,
    ) -> None:
        """Wire the ports."""
        self._mail = mailbox
        self._store = store
        self._lock = lock
        self._notifier = notifier
        self._archive = archive_label
        self._batch = batch_size

    async def run_once(self) -> None:
        """Process every open request of an applied plan."""
        for job in await self._store.pending_requests():
            if job.plan_state is not PlanState.APPLIED:
                continue
            run_id = uuid.uuid4().hex
            if await self._store.claim_request(job.plan_id, run_id):
                await self._restore_plan(job, run_id)

    async def _restore_plan(self, job: MoveBackJob, run_id: str) -> None:
        moves = await self._store.audit_moves(job.plan_id)
        restored = skipped = 0
        for start in range(0, len(moves), self._batch):
            if await self._lock.is_locked():
                logger.info("move back stopped by the lock plan=%s", job.plan_id)
                return  # the request stays open; a later run continues
            if not await self._store.renew_request(job.plan_id, run_id):
                return
            names = await asyncio.to_thread(self._mail.label_names)
            for move in moves[start : start + self._batch]:
                if await self._restore_one(job, move, names):
                    restored += 1
                else:
                    skipped += 1
        if await self._store.finish_request(job.plan_id, run_id):
            logger.info("move back done plan=%s restored=%d skipped=%d", job.plan_id, restored, skipped)
            await self._notifier.say(
                f"Move back done: {restored} restored, {skipped} skipped because they changed meanwhile."
            )

    async def _restore_one(self, job: MoveBackJob, move: AuditMove, names: dict[str, str]) -> bool:
        """True when the mail carries its old label afterwards; false when it was changed and is left alone."""
        mail = await asyncio.to_thread(self._mail.fetch, move.message_id)
        if mail is None:
            return False
        held = held_label_ids(mail, names)
        old = move.old_label
        if move.new_label not in held:
            return held == ({old} if old else set())  # already back (a retry, or the user did it)
        if held - {move.new_label, old}:
            return False  # another label as well: changed meanwhile
        if (
            old not in held
            and classify({names[i] for i in mail.labels if i in names}, self._archive) is not Scope.IN_SCOPE
        ):
            return False  # archived, trashed or out of the inbox meanwhile
        try:
            if old and old not in held:
                await asyncio.to_thread(self._mail.add_label, move.message_id, old)
            await asyncio.to_thread(self._mail.remove_label, move.message_id, move.new_label)
        except (MailGone, MailFailed):
            return False  # gone, or Gmail keeps refusing this one: the request must still finish
        await self._store.record_restore(job.plan_id, AuditMove(move.message_id, move.new_label, old), job.channel)
        return True
