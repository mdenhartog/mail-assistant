"""The delayed-apply notice and the move-back request in PostgreSQL (INT-004, ADR-0046; ports of ``approval_notice``).

Every state change is one compare-and-set statement on ``plan``. The agent asks for a move back as itself: the trigger
of ``move_back_request`` refuses a plan that is not ``applied`` and writes the actor and the time (ADR-0030).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import aliased

from app.core.resort_plan import PlanKind, PlanState
from app.db.models import ApplyConfig, CategoryMailbox, MoveBackRequest, Plan, PlanApproval, PlanItem
from app.usecases.approval_notice import CancelOutcome, ScheduledPlan

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["PgApprovalStore", "PgMoveBackRequests"]

_NOT_ALLOWED: Final = "MC409"  # the database's refusal of a state that does not allow the request


class PgApprovalStore:
    """``ApprovalStore`` on ``plan``."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    async def write_config(self, *, threshold: int, delay_minutes: int) -> None:
        """Store the approval threshold and delay of the deployment where ``approve_plan`` reads them.

        The mailbox row is made when missing (a list sync may not have run yet); an existing row is replaced.
        """
        mailbox = insert(CategoryMailbox).values(id=self._mailbox).on_conflict_do_nothing()
        config = insert(ApplyConfig).values(mailbox_id=self._mailbox, threshold=threshold, delay_minutes=delay_minutes)
        config = config.on_conflict_do_update(
            index_elements=[ApplyConfig.mailbox_id],
            set_={"threshold": config.excluded.threshold, "delay_minutes": config.excluded.delay_minutes},
        )
        async with self._sessions.begin() as session:
            await session.execute(mailbox)
            await session.execute(config)

    async def unannounced(self) -> list[ScheduledPlan]:
        """``scheduled`` plans with a delay (the apply starts after the approval) and no notice yet."""
        approved_at = (
            select(func.max(PlanApproval.at))
            .where(PlanApproval.mailbox_id == Plan.mailbox_id, PlanApproval.plan_id == Plan.id)
            .scalar_subquery()
        )
        items = (
            select(func.count())
            .select_from(PlanItem)
            .where(PlanItem.mailbox_id == Plan.mailbox_id, PlanItem.plan_id == Plan.id, PlanItem.state == "approved")
            .scalar_subquery()
        )
        review = aliased(Plan)
        waiting = (  # items of the request's review plan that wait for the user; only an ``auto`` plan has one
            select(func.count())
            .select_from(PlanItem)
            .join(review, and_(review.mailbox_id == PlanItem.mailbox_id, review.id == PlanItem.plan_id))
            .where(
                review.mailbox_id == Plan.mailbox_id,
                review.request_id == Plan.request_id,
                review.kind == PlanKind.REVIEW.value,
                Plan.kind == PlanKind.AUTO.value,
                PlanItem.state == "pending",
            )
            .scalar_subquery()
        )
        statement = (
            select(Plan.id, items, Plan.apply_after, Plan.kind, waiting)
            .where(
                Plan.mailbox_id == self._mailbox,
                Plan.state == PlanState.SCHEDULED.value,
                Plan.announced_at.is_(None),
                Plan.apply_after > approved_at,
            )
            .order_by(Plan.created_at)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            ScheduledPlan(plan_id, count, after, PlanKind(kind), waiting_count)
            for plan_id, count, after, kind, waiting_count in rows
            if after is not None
        ]

    async def mark_announced(self, plan_id: uuid.UUID) -> None:
        """Remember that the notice of the plan was sent."""
        statement = (
            update(Plan).where(Plan.mailbox_id == self._mailbox, Plan.id == plan_id).values(announced_at=func.now())
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def cancel_before_start(self, plan_id: uuid.UUID) -> CancelOutcome:
        """``scheduled`` to ``cancelled`` while the database clock is before ``apply_after``; else say why not."""
        mine = and_(Plan.mailbox_id == self._mailbox, Plan.id == plan_id)
        cancel = (
            update(Plan)
            .where(mine, Plan.state == PlanState.SCHEDULED.value, Plan.apply_after > func.now())
            .values(state=PlanState.CANCELLED.value, apply_lease_until=None)
            .returning(Plan.id)
        )
        async with self._sessions.begin() as session:
            if (await session.execute(cancel)).first() is not None:
                return CancelOutcome.CANCELLED
            state = (await session.execute(select(Plan.state).where(mine))).scalar_one_or_none()
        return CancelOutcome.TOO_LATE if state == PlanState.SCHEDULED.value else CancelOutcome.NOT_SCHEDULED

    async def cancel_open_plans(self) -> int:
        """Every ``scheduled`` or ``applying`` plan of the mailbox to ``cancelled``; return how many."""
        statement = (
            update(Plan)
            .where(
                Plan.mailbox_id == self._mailbox,
                Plan.state.in_((PlanState.SCHEDULED.value, PlanState.APPLYING.value)),
            )
            .values(state=PlanState.CANCELLED.value, apply_lease_until=None)
            .returning(Plan.id)
        )
        async with self._sessions.begin() as session:
            return len((await session.execute(statement)).all())


class PgMoveBackRequests:
    """``MoveBackRequests`` on ``move_back_request``."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    async def request(self, plan_id: uuid.UUID) -> bool:
        """Ask for the restore of an ``applied`` plan; ``False`` when it is not applied or was asked already."""
        statement = (
            insert(MoveBackRequest)
            .values(mailbox_id=self._mailbox, plan_id=plan_id)
            .on_conflict_do_nothing()
            .returning(MoveBackRequest.plan_id)
        )
        try:
            async with self._sessions.begin() as session:
                return (await session.execute(statement)).first() is not None
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) == _NOT_ALLOWED:
                return False
            raise
