"""The plan build, the apply and the move back in PostgreSQL (INT-004, ADR-0046, ADR-0047, ADR-0043).

One store per mailbox: every statement filters on ``mailbox_id``. The agent role may do exactly these writes
(``app/db/grants.sql``): create, advance and complete a plan, add items, move an item through apply with ``state``,
``reason`` and ``attempts`` only, append audit rows and take a lease on a plan or a move-back request. It never sets a
decision, never deletes a row, and never supplies the time, the actor or (for an apply) the channel of an audit row: the
database derives the actor and the time (ADR-0030) and the apply channel comes from the approval of the plan.

Every state change is one compare-and-set statement, so two agent processes cannot both win. A plan being applied and a
move-back request carry a lease (run id and expiry, both from the database clock): a crashed run's lease ends and a
later run takes the work over.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import and_, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.judgement import ListedCategory
from app.core.resort_plan import ItemState, PlanState
from app.db.migrate import RUNTIME_ROLE, WEB_ROLE
from app.db.models import (
    ApplyAudit,
    Category,
    ListVersion,
    MoveBackRequest,
    Plan,
    PlanApproval,
    PlanItem,
    Rejection,
)
from app.usecases.move_back import MoveBackJob
from app.usecases.resort_apply import ApplyItem, AuditMove, DuePlan
from app.usecases.resort_build import BuildList, ItemDraft, PlanRecord

if TYPE_CHECKING:
    import uuid

    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.usecases.resort_apply import SkipReason

__all__ = ["LEASE", "PgApplyStore", "PgBuildStore", "channel_of"]

LEASE: Final = timedelta(minutes=5)  # how long a run holds a plan or a request before another may take it over
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_DIGESTS: Final = {
    hashlib.sha256(WEB_ROLE.encode()).hexdigest(): "web",
    hashlib.sha256(RUNTIME_ROLE.encode()).hexdigest(): "telegram",
}


def channel_of(actor_digest: str) -> str:
    """The channel of a request from the digest of the login that wrote it (the database derives both the same way)."""
    return _DIGESTS.get(actor_digest.strip(), "operator")


def _record(plan: Plan, items: int) -> PlanRecord:
    return PlanRecord(
        plan.id,
        plan.list_version,
        PlanState(plan.state),
        plan.build_cursor,
        plan.checked_count,
        plan.unclear_count,
        items,
        plan.cap,
    )


class PgBuildStore:
    """``BuildStore`` on the list tables and ``plan``."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    def _mine(self, plan_id: uuid.UUID) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
        return Plan.mailbox_id == self._mailbox, Plan.id == plan_id

    async def current_list(self) -> BuildList:
        """The latest list version with its categories in order; version 0 when there is none."""
        newest = (
            select(ListVersion.version, ListVersion.created_at)
            .where(ListVersion.mailbox_id == self._mailbox)
            .order_by(ListVersion.version.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            row = (await session.execute(newest)).first()
            if row is None:
                return BuildList(0, _EPOCH, ())
            categories = await session.execute(
                select(Category.id, Category.name, Category.description)
                .where(Category.mailbox_id == self._mailbox, Category.version == row.version)
                .order_by(Category.position)
            )
            return BuildList(
                row.version, row.created_at, tuple(_listed(c.id, c.name, c.description) for c in categories)
            )

    async def latest_plan(self) -> PlanRecord | None:
        """The newest plan of the mailbox, terminal or not."""
        items = (
            select(func.count())
            .select_from(PlanItem)
            .where(PlanItem.mailbox_id == Plan.mailbox_id, PlanItem.plan_id == Plan.id)
            .scalar_subquery()
        )
        statement = (
            select(Plan, items)
            .where(Plan.mailbox_id == self._mailbox)
            .order_by(Plan.created_at.desc(), Plan.id.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            row = (await session.execute(statement)).first()
        return None if row is None else _record(row[0], row[1])

    async def replace_plan(self, plan_id: uuid.UUID) -> bool:
        """Compare-and-set ``building`` or ``ready`` to ``replaced`` and drop its items (one database function)."""
        statement = select(func.categories.replace_plan(self._mailbox, plan_id))
        async with self._sessions.begin() as session:
            return bool((await session.execute(statement)).scalar_one())

    async def record_estimate(self, plan_id: uuid.UUID, estimate: int) -> None:
        """Store the estimated number of mails in scope."""
        statement = update(Plan).where(*self._mine(plan_id)).values(estimate_total=estimate)
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def complete_build(self, plan_id: uuid.UUID, *, not_looked_at: int) -> bool:
        """Compare-and-set ``building`` to ``ready``; true for the one caller that did it."""
        statement = (
            update(Plan)
            .where(*self._mine(plan_id), Plan.state == PlanState.BUILDING.value)
            .values(state=PlanState.READY.value, not_looked_at=not_looked_at, last_activity_at=func.now())
            .returning(Plan.id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None

    async def rejected_ids(self, list_version: int) -> frozenset[str]:
        """Mail the user rejected under this list version."""
        statement = select(Rejection.message_id).where(
            Rejection.mailbox_id == self._mailbox, Rejection.list_version == list_version
        )
        async with self._sessions() as session:
            return frozenset((await session.execute(statement)).scalars())

    async def record_progress(
        self, plan_id: uuid.UUID, *, item: ItemDraft | None, cursor: str, checked: int, unclear: int
    ) -> bool:
        """In one transaction add the item, the counts and the cursor; false when the plan is no longer ``building``.

        The update comes first and locks the plan row: a replace waits for this transaction and then drops the item,
        and a plan that was replaced before gets nothing.
        """
        progress = (
            update(Plan)
            .where(*self._mine(plan_id), Plan.state == PlanState.BUILDING.value)
            .values(
                build_cursor=cursor,
                checked_count=Plan.checked_count + checked,
                unclear_count=Plan.unclear_count + unclear,
                last_activity_at=func.now(),
            )
            .returning(Plan.id)
        )
        async with self._sessions.begin() as session:
            if (await session.execute(progress)).first() is None:
                return False
            if item is not None:
                await session.execute(
                    insert(PlanItem)
                    .values(
                        mailbox_id=self._mailbox,
                        plan_id=plan_id,
                        message_id=item.message_id,
                        sender_name=item.sender_name,
                        sender_address=item.sender_address,
                        subject=item.subject,
                        old_category_id=item.old_category_id,
                        new_category_id=item.new_category_id,
                    )
                    .on_conflict_do_nothing(constraint="uq_plan_item_message")  # a mail listed twice stays one item
                )
        return True


def _listed(category_id: uuid.UUID, name: str, description: str) -> ListedCategory:
    return ListedCategory(str(category_id), name, description)


class PgApplyStore:
    """``ApplyStore`` and ``MoveBackStore`` on ``plan``, ``plan_item``, ``apply_audit`` and ``move_back_request``."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str, *, lease: timedelta = LEASE
    ) -> None:
        """Keep the session factory, the mailbox and how long a lease lasts."""
        self._sessions = sessions
        self._mailbox = mailbox_id
        self._lease = lease

    def _plan(self, plan_id: uuid.UUID) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
        return Plan.mailbox_id == self._mailbox, Plan.id == plan_id

    # --- ApplyStore -------------------------------------------------------------------------------------------------

    async def plans_to_apply(self) -> list[DuePlan]:
        """Plans that are ``scheduled`` or ``applying``, with the channel and actor of their latest approval."""
        statement = select(Plan).where(
            Plan.mailbox_id == self._mailbox,
            Plan.state.in_((PlanState.SCHEDULED.value, PlanState.APPLYING.value)),
        )
        found: list[DuePlan] = []
        async with self._sessions() as session:
            for plan in (await session.execute(statement)).scalars():
                approval = (
                    await session.execute(
                        select(PlanApproval.channel, PlanApproval.actor_digest)
                        .where(PlanApproval.mailbox_id == self._mailbox, PlanApproval.plan_id == plan.id)
                        .order_by(PlanApproval.at.desc(), PlanApproval.id.desc())
                        .limit(1)
                    )
                ).first()
                if approval is not None:  # a plan nobody approved is never applied
                    found.append(
                        DuePlan(
                            plan.id, PlanState(plan.state), plan.apply_after, approval.channel, approval.actor_digest
                        )
                    )
        return found

    async def claim(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """``scheduled`` (due; announced when delayed) to ``applying``, or take over an old ``applying`` lease."""
        free = or_(Plan.apply_lease_until.is_(None), Plan.apply_lease_until <= func.now())
        approved_at = (
            select(func.max(PlanApproval.at))
            .where(PlanApproval.mailbox_id == Plan.mailbox_id, PlanApproval.plan_id == Plan.id)
            .scalar_subquery()
        )
        # a delayed plan (the apply starts after the approval) waits for its notice: nobody could cancel before it
        announced = or_(Plan.announced_at.is_not(None), Plan.apply_after <= approved_at)
        takeable = or_(
            and_(Plan.state == PlanState.SCHEDULED.value, Plan.apply_after <= func.now(), announced),
            and_(Plan.state == PlanState.APPLYING.value, free),
        )
        statement = (
            update(Plan)
            .where(*self._plan(plan_id), takeable)
            .values(
                state=PlanState.APPLYING.value,
                apply_run_id=run_id,
                apply_lease_until=func.now() + self._lease,
                last_activity_at=func.now(),
            )
            .returning(Plan.id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None

    async def begin_batch(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """True while the plan is ``applying`` and this run holds it; renews the lease."""
        statement = (
            update(Plan)
            .where(*self._plan(plan_id), Plan.state == PlanState.APPLYING.value, Plan.apply_run_id == run_id)
            .values(apply_lease_until=func.now() + self._lease, last_activity_at=func.now())
            .returning(Plan.id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None

    async def cancel(self, plan_id: uuid.UUID) -> bool:
        """``scheduled`` or ``applying`` to ``cancelled``; false when the plan was already something else."""
        statement = (
            update(Plan)
            .where(*self._plan(plan_id), Plan.state.in_((PlanState.SCHEDULED.value, PlanState.APPLYING.value)))
            .values(state=PlanState.CANCELLED.value, apply_lease_until=None)
            .returning(Plan.id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None

    async def current_categories(self) -> dict[str, str]:
        """Category id to name of the latest list version."""
        latest = select(func.max(ListVersion.version)).where(ListVersion.mailbox_id == self._mailbox).scalar_subquery()
        statement = select(Category.id, Category.name).where(
            Category.mailbox_id == self._mailbox, Category.version == latest
        )
        async with self._sessions() as session:
            return {str(row.id): row.name for row in await session.execute(statement)}

    async def next_items(self, plan_id: uuid.UUID, limit: int) -> list[ApplyItem]:
        """Up to ``limit`` items still ``approved``, in the order they were planned."""
        statement = (
            select(PlanItem.message_id, PlanItem.old_category_id, PlanItem.new_category_id)
            .where(
                PlanItem.mailbox_id == self._mailbox,
                PlanItem.plan_id == plan_id,
                PlanItem.state == ItemState.APPROVED.value,
            )
            .order_by(PlanItem.id)
            .limit(limit)
        )
        async with self._sessions() as session:
            return [
                ApplyItem(r.message_id, r.old_category_id, r.new_category_id) for r in await session.execute(statement)
            ]

    async def intent_for(self, plan_id: uuid.UUID, message_id: str) -> AuditMove | None:
        """The apply audit row of this plan and mail, when one exists."""
        statement = select(ApplyAudit.message_id, ApplyAudit.old_label, ApplyAudit.new_label).where(
            *self._audit(plan_id), ApplyAudit.message_id == message_id
        )
        async with self._sessions() as session:
            row = (await session.execute(statement)).first()
        return None if row is None else AuditMove(row.message_id, row.old_label, row.new_label)

    def _audit(self, plan_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
        return ApplyAudit.mailbox_id == self._mailbox, ApplyAudit.plan_id == plan_id, ApplyAudit.kind == "apply"

    async def record_intent(self, plan_id: uuid.UUID, move: AuditMove) -> None:
        """Insert the apply row unless one exists; its channel is the one of the plan's latest approval.

        The actor and the time are the database's. A plan without approval has no channel: that is refused, so no mail
        is ever moved without an attributable audit row.
        """
        approval = (
            select(
                literal(self._mailbox),
                literal(plan_id),
                literal(move.message_id),
                literal(move.old_label),
                literal(move.new_label),
                PlanApproval.channel,
                literal("apply"),
            )
            .where(PlanApproval.mailbox_id == self._mailbox, PlanApproval.plan_id == plan_id)
            .order_by(PlanApproval.at.desc(), PlanApproval.id.desc())
            .limit(1)
        )
        statement = (
            insert(ApplyAudit)
            .from_select(["mailbox_id", "plan_id", "message_id", "old_label", "new_label", "channel", "kind"], approval)
            .on_conflict_do_nothing()
            .returning(ApplyAudit.id)
        )
        async with self._sessions.begin() as session:
            inserted = (await session.execute(statement)).first() is not None
        if not inserted and await self.intent_for(plan_id, move.message_id) is None:
            raise LookupError("the plan has no approval, so no move can be attributed")

    async def finish_item(
        self, plan_id: uuid.UUID, message_id: str, state: ItemState, reason: SkipReason | None
    ) -> bool:
        """Compare-and-set ``approved`` to ``applied``, ``skipped`` or ``failed`` with the reason."""
        statement = (
            update(PlanItem)
            .where(
                PlanItem.mailbox_id == self._mailbox,
                PlanItem.plan_id == plan_id,
                PlanItem.message_id == message_id,
                PlanItem.state == ItemState.APPROVED.value,
            )
            .values(state=state.value, reason=None if reason is None else reason.value)
            .returning(PlanItem.id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None

    async def count_attempt(self, plan_id: uuid.UUID, message_id: str) -> int:
        """Count one failed move of an item still ``approved``; a decided item keeps its count, which is returned."""
        statement = (
            update(PlanItem)
            .where(
                PlanItem.mailbox_id == self._mailbox,
                PlanItem.plan_id == plan_id,
                PlanItem.message_id == message_id,
                PlanItem.state == ItemState.APPROVED.value,
            )
            .values(attempts=PlanItem.attempts + 1)
            .returning(PlanItem.attempts)
        )
        async with self._sessions.begin() as session:
            counted = (await session.execute(statement)).scalar_one_or_none()
            if counted is not None:
                return counted
            stored = select(PlanItem.attempts).where(
                PlanItem.mailbox_id == self._mailbox, PlanItem.plan_id == plan_id, PlanItem.message_id == message_id
            )
            return (await session.execute(stored)).scalar_one_or_none() or 0

    async def finish_plan(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """Compare-and-set ``applying`` to ``applied`` for the lease holder; true for exactly one caller."""
        statement = (
            update(Plan)
            .where(*self._plan(plan_id), Plan.state == PlanState.APPLYING.value, Plan.apply_run_id == run_id)
            .values(state=PlanState.APPLIED.value, apply_lease_until=None, last_activity_at=func.now())
            .returning(Plan.id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None

    async def item_counts(self, plan_id: uuid.UUID) -> dict[ItemState, int]:
        """Items per state."""
        statement = (
            select(PlanItem.state, func.count())
            .where(PlanItem.mailbox_id == self._mailbox, PlanItem.plan_id == plan_id)
            .group_by(PlanItem.state)
        )
        async with self._sessions() as session:
            return {ItemState(state): count for state, count in await session.execute(statement)}

    async def remove_applied_items(self, plan_id: uuid.UUID) -> None:
        """Delete the applied items of an applied plan (one database function: the agent has no DELETE right)."""
        statement = select(func.categories.remove_applied_items(self._mailbox, plan_id))
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def audit_moves(self, plan_id: uuid.UUID) -> list[AuditMove]:
        """The apply rows of the plan, never the restore rows a move back wrote under the same plan."""
        statement = (
            select(ApplyAudit.message_id, ApplyAudit.old_label, ApplyAudit.new_label)
            .where(*self._audit(plan_id))
            .order_by(ApplyAudit.id)
        )
        async with self._sessions() as session:
            return [AuditMove(r.message_id, r.old_label, r.new_label) for r in await session.execute(statement)]

    # --- MoveBackStore ----------------------------------------------------------------------------------------------

    async def pending_requests(self) -> list[MoveBackJob]:
        """Requests not yet processed, with the channel derived from the login that asked."""
        statement = (
            select(MoveBackRequest.plan_id, Plan.state, MoveBackRequest.actor_digest)
            .join(Plan, and_(Plan.mailbox_id == MoveBackRequest.mailbox_id, Plan.id == MoveBackRequest.plan_id))
            .where(MoveBackRequest.mailbox_id == self._mailbox, MoveBackRequest.processed.is_(False))
            .order_by(MoveBackRequest.at)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [MoveBackJob(r.plan_id, PlanState(r.state), channel_of(r.actor_digest), r.actor_digest) for r in rows]

    def _request(self, plan_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
        return (
            MoveBackRequest.mailbox_id == self._mailbox,
            MoveBackRequest.plan_id == plan_id,
            MoveBackRequest.processed.is_(False),
        )

    async def claim_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """Take the request when it is open and no other run holds its lease."""
        statement = (
            update(MoveBackRequest)
            .where(
                *self._request(plan_id),
                or_(MoveBackRequest.lease_until.is_(None), MoveBackRequest.lease_until <= func.now()),
            )
            .values(run_id=run_id, lease_until=func.now() + self._lease)
            .returning(MoveBackRequest.plan_id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None

    async def renew_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """True while this run holds the lease of an open request; renews it."""
        statement = (
            update(MoveBackRequest)
            .where(*self._request(plan_id), MoveBackRequest.run_id == run_id)
            .values(lease_until=func.now() + self._lease)
            .returning(MoveBackRequest.plan_id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None

    async def record_restore(self, plan_id: uuid.UUID, move: AuditMove, channel: str) -> None:
        """Insert a restore row (old and new swapped by the caller) with the channel of the request."""
        statement = insert(ApplyAudit).values(
            mailbox_id=self._mailbox,
            plan_id=plan_id,
            message_id=move.message_id,
            old_label=move.old_label,
            new_label=move.new_label,
            channel=channel,
            kind="restore",
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def finish_request(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """Compare-and-set the request to processed for the lease holder; true for exactly one caller."""
        statement = (
            update(MoveBackRequest)
            .where(*self._request(plan_id), MoveBackRequest.run_id == run_id)
            .values(processed=True, lease_until=None)
            .returning(MoveBackRequest.plan_id)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).first() is not None
