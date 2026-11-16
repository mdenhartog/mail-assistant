"""Read and write access to the review plan as the web role (U-mail-categories-17, ADR-0044, ADR-0046, ADR-0047).

Every query filters on the mailbox id. Decisions and the approval go through the database functions only; the move-back
request is one insert. Sender and subject are read from ``plan_item`` and handed to the response, nowhere else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime  # datetime is used at run time to normalise the zone
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    import uuid

    from app.db import Database
    from app.plan_models import Decision

_CONFLICT = "MC409"  # a plan, count, group, id or state mismatch (the 409 of the design)
_MALFORMED = "22023"  # a malformed argument

_OPEN_PLAN = text(
    "SELECT id, state, apply_after, checked_count, cap, unclear_count, estimate_total, not_looked_at "
    "FROM categories.plan "
    "WHERE mailbox_id = :mailbox AND state IN ('building', 'ready', 'scheduled', 'applying')"
)
# The plan that ended most recently and is still kept (the purge removes the rest); a discarded one is not shown.
# For an applied plan the apply removes the items it moved and adds their number to ``moved_count``; items still there
# are added. A cancelled or replaced plan moved nothing.
_LAST_ENDED = text(
    "SELECT p.id, p.state, p.terminal_at, CASE WHEN p.state = 'applied' THEN p.moved_count + ("
    "SELECT count(*) FROM categories.plan_item i "
    "WHERE i.mailbox_id = p.mailbox_id AND i.plan_id = p.id AND i.state = 'applied') ELSE 0 END AS moved "
    "FROM categories.plan p WHERE p.mailbox_id = :mailbox AND p.state IN ('applied', 'cancelled', 'replaced') "
    "ORDER BY p.terminal_at DESC NULLS LAST, p.created_at DESC LIMIT 1"
)
_APPLY_CONFIG = text("SELECT threshold, delay_minutes FROM categories.apply_config WHERE mailbox_id = :mailbox")
_GROUPS = text(
    "SELECT g.old_category_id, g.new_category_id, g.n, g.approved, g.rejected, "
    "e.sender_name, e.sender_address, e.subject FROM ("
    "SELECT old_category_id, new_category_id, count(*) AS n, "
    "count(*) FILTER (WHERE decision = 'approved') AS approved, "
    "count(*) FILTER (WHERE decision = 'rejected') AS rejected, min(id) AS first_id "
    "FROM categories.plan_item WHERE mailbox_id = :mailbox AND plan_id = :plan "
    "GROUP BY old_category_id, new_category_id) g "
    "JOIN categories.plan_item e ON e.mailbox_id = :mailbox AND e.plan_id = :plan AND e.id = g.first_id "
    "ORDER BY g.n DESC, g.old_category_id, g.new_category_id"
)
_DECISIONS = text(
    "SELECT decision, count(*) AS n FROM categories.plan_item "
    "WHERE mailbox_id = :mailbox AND plan_id = :plan GROUP BY decision"
)
_ITEMS = text(
    "SELECT id, sender_name, sender_address, subject, old_category_id, new_category_id, decision, state, reason "
    "FROM categories.plan_item WHERE mailbox_id = :mailbox AND plan_id = :plan "
    "AND (CAST(:from_id AS uuid) IS NULL OR old_category_id = CAST(:from_id AS uuid)) "
    "AND (CAST(:to_id AS uuid) IS NULL OR new_category_id = CAST(:to_id AS uuid)) "
    "ORDER BY id LIMIT :limit OFFSET :offset"
)
_DECIDE = text("SELECT categories.record_decision(:mailbox, :plan, :count, CAST(:scope AS jsonb), :decision)")
_APPROVE = text("SELECT state, apply_after FROM categories.approve_plan(:mailbox, :plan, :count)")
_MOVE_BACK = text(
    "INSERT INTO categories.move_back_request (mailbox_id, plan_id) VALUES (:mailbox, :plan) "
    "ON CONFLICT (mailbox_id, plan_id) DO NOTHING"
)
_MOVE_BACK_STATE = text(
    "SELECT processed FROM categories.move_back_request WHERE mailbox_id = :mailbox AND plan_id = :plan"
)


class PlanConflict(Exception):  # noqa: N818  # a state of the plan, not a fault of the caller
    """The plan, the item count, the group, an id or the state does not match; nothing was written."""


class PlanMalformed(Exception):  # noqa: N818  # the database refused the shape of an argument
    """The database function refused an argument as malformed; nothing was written."""


@dataclass(frozen=True, slots=True)
class OpenPlan:
    """The plan that is not finished yet."""

    id: uuid.UUID
    state: str
    apply_after: datetime | None
    checked: int
    cap: int
    unclear: int
    estimate: int | None
    not_looked_at: int


@dataclass(frozen=True, slots=True)
class EndedPlan:
    """A plan that ended (applied, cancelled or replaced), how and when."""

    id: uuid.UUID
    state: str
    ended_at: datetime | None
    moved: int


@dataclass(frozen=True, slots=True)
class GroupRow:
    """A group of items."""

    old_id: uuid.UUID
    new_id: uuid.UUID
    count: int
    approved: int
    rejected: int
    sender_name: str
    sender_address: str
    subject: str


@dataclass(frozen=True, slots=True)
class ItemRow:
    """An item as the page shows it."""

    id: int
    sender_name: str
    sender_address: str
    subject: str
    old_id: uuid.UUID
    new_id: uuid.UUID
    decision: str
    state: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class PlanSnapshot:
    """The open plan with its groups and decision counts, and the plan that ended last."""

    open: OpenPlan | None
    groups: tuple[GroupRow, ...]
    decisions: dict[str, int]
    last_ended: EndedPlan | None
    apply_threshold: int | None
    apply_delay_minutes: int | None


@dataclass(frozen=True, slots=True)
class ItemsPage:
    """One page of items; ``has_more`` when there is a next page."""

    items: tuple[ItemRow, ...]
    has_more: bool


def _utc(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(UTC)


def _sqlstate(error: BaseException | None) -> str | None:
    while error is not None:
        for name in ("sqlstate", "pgcode"):
            value = getattr(error, name, None)
            if isinstance(value, str):
                return value
        error = error.__cause__
    return None


def refusal_of(error: DBAPIError) -> Exception | None:
    """Translate the SQLSTATE of a refused database function call.

    Args:
        error: The driver error.

    Returns:
        ``PlanConflict`` for the 409 state, ``PlanMalformed`` for a malformed argument, None for anything else (which
        stays a server fault and is not translated).
    """
    state = _sqlstate(error.orig)
    if state == _CONFLICT:
        return PlanConflict()
    if state == _MALFORMED:
        return PlanMalformed()
    return None


def _raise_refusal(error: DBAPIError) -> None:
    """Raise the refusal of a database function, or the error itself when it is not one. Never chained."""
    refusal = refusal_of(error)
    if refusal is None:
        raise error
    raise refusal from None  # not chained: the driver text may carry what was asked


class PlanRepository:
    """Reads the plan of one mailbox and calls the functions that change it."""

    def __init__(self, database: Database, mailbox_id: str) -> None:
        """Keep the database access and the mailbox every query is limited to."""
        self._database = database
        self._mailbox = mailbox_id

    async def snapshot(self) -> PlanSnapshot:
        """Read the open plan, its groups and decision counts, and the plan that ended most recently.

        Returns:
            The snapshot; no open plan when there is none.
        """
        params: dict[str, Any] = {"mailbox": self._mailbox}
        async with self._database.session() as session, session.begin():
            row = (await session.execute(_OPEN_PLAN, params)).first()
            ended = (await session.execute(_LAST_ENDED, params)).first()
            config = (await session.execute(_APPLY_CONFIG, params)).first()
            open_plan = (
                None
                if row is None
                else OpenPlan(
                    row.id,
                    row.state,
                    _utc(row.apply_after),
                    row.checked_count,
                    row.cap,
                    row.unclear_count,
                    row.estimate_total,
                    row.not_looked_at,
                )
            )
            groups: tuple[GroupRow, ...] = ()
            decisions: dict[str, int] = {}
            if open_plan is not None:
                scope = {**params, "plan": open_plan.id}
                groups = tuple(
                    GroupRow(
                        g.old_category_id,
                        g.new_category_id,
                        g.n,
                        g.approved,
                        g.rejected,
                        g.sender_name,
                        g.sender_address,
                        g.subject,
                    )
                    for g in await session.execute(_GROUPS, scope)
                )
                decisions = {d.decision: d.n for d in await session.execute(_DECISIONS, scope)}
        last = None if ended is None else EndedPlan(ended.id, ended.state, _utc(ended.terminal_at), ended.moved)
        return PlanSnapshot(
            open_plan,
            groups,
            decisions,
            last,
            None if config is None else config.threshold,
            None if config is None else config.delay_minutes,
        )

    async def items(self, page: int, page_size: int, from_id: uuid.UUID | None, to_id: uuid.UUID | None) -> ItemsPage:
        """Read one page of the open plan's items, lowest id first.

        Args:
            page: The page, from 1.
            page_size: The most items on a page.
            from_id: Only items that leave this category, or None.
            to_id: Only items that go to this category, or None.

        Returns:
            The items and whether another page follows; empty when there is no open plan.
        """
        async with self._database.session() as session, session.begin():
            plan = (await session.execute(_OPEN_PLAN, {"mailbox": self._mailbox})).first()
            if plan is None:
                return ItemsPage((), has_more=False)
            params: dict[str, Any] = {
                "mailbox": self._mailbox,
                "plan": plan.id,
                "from_id": from_id,
                "to_id": to_id,
                "limit": page_size + 1,
                "offset": (page - 1) * page_size,
            }
            rows = (await session.execute(_ITEMS, params)).all()
        items = tuple(
            ItemRow(
                r.id,
                r.sender_name,
                r.sender_address,
                r.subject,
                r.old_category_id,
                r.new_category_id,
                r.decision,
                r.state,
                r.reason,
            )
            for r in rows[:page_size]
        )
        return ItemsPage(items, has_more=len(rows) > page_size)

    async def decide(self, plan_id: uuid.UUID, count: int, scope: dict[str, Any], decision: Decision) -> int:
        """Record a decision through ``record_decision``.

        Args:
            plan_id: The plan the user saw.
            count: The item count the user saw.
            scope: The scope in the shape the function takes (``kind`` and its fields).
            decision: ``approved`` or ``rejected``.

        Returns:
            The number of items changed.

        Raises:
            PlanConflict: The plan, count, group, an id or the state does not match; nothing changed.
            PlanMalformed: The function refused an argument.
        """
        params = {
            "mailbox": self._mailbox,
            "plan": plan_id,
            "count": count,
            "scope": json.dumps(scope),
            "decision": decision,
        }
        try:
            async with self._database.session() as session, session.begin():
                return int((await session.execute(_DECIDE, params)).scalar_one())
        except DBAPIError as error:
            _raise_refusal(error)
            raise  # unreachable: _raise_refusal always raises

    async def approve(self, plan_id: uuid.UUID, count: int) -> tuple[str, datetime | None]:
        """Approve the plan through ``approve_plan``; a plan that is already scheduled returns its state.

        Args:
            plan_id: The plan the user saw.
            count: The item count the user saw.

        Returns:
            The state and the time the apply may start.

        Raises:
            PlanConflict: The plan, count or state does not match, or the apply settings are missing; nothing changed.
            PlanMalformed: The function refused an argument.
        """
        params = {"mailbox": self._mailbox, "plan": plan_id, "count": count}
        try:
            async with self._database.session() as session, session.begin():
                row = (await session.execute(_APPROVE, params)).one()
        except DBAPIError as error:
            _raise_refusal(error)
            raise  # unreachable: _raise_refusal always raises
        return row.state, _utc(row.apply_after)

    async def move_back(self, plan_id: uuid.UUID) -> bool:
        """Store the move-back request of an applied plan; a repeat stores nothing new.

        Args:
            plan_id: The plan to move back.

        Returns:
            Whether the agent has processed the request.

        Raises:
            PlanConflict: The plan is not an applied plan of this mailbox; nothing was stored.
        """
        params = {"mailbox": self._mailbox, "plan": plan_id}
        try:
            async with self._database.session() as session, session.begin():
                await session.execute(_MOVE_BACK, params)
                return bool((await session.execute(_MOVE_BACK_STATE, params)).scalar_one())
        except DBAPIError as error:
            _raise_refusal(error)
            raise  # unreachable: _raise_refusal always raises
