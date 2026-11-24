"""The database side of the daily re-file report (INT-004, AC-46, ADR-0043).

One store per mailbox: every statement filters on ``mailbox_id``. The agent role reads ``filing``,
``managed_label``, ``plan`` and ``apply_audit`` and writes the report only through
``categories.record_refile_report``; it has no right on the report table itself
(``app/db/grants.sql``). No statement here is built from a string.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.dialects.postgresql import distinct_on

from app.core.judgement import OTHER_ID
from app.core.resort_plan import PlanKind
from app.db.models import Alert, ApplyAudit, Filing, Plan
from app.db.pg_resort import read_managed_labels
from app.usecases.refile_report import PERIOD, Filed
from app.usecases.report import SuccessCounts

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.usecases.refile_report import RefileReport
    from app.usecases.resort_apply import ResortLabels

__all__ = ["PgRefileStore"]


class PgRefileStore:
    """``RefileStore`` on PostgreSQL. Each call is its own transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], mailbox_id: str) -> None:
        """Keep the session factory and the mailbox this store works for."""
        self._sessions = sessions
        self._mailbox = mailbox_id

    async def filings_since(self, since: datetime) -> list[Filed]:
        """The newest ``filing`` row of each mail filed since ``since``, the most recently filed first."""
        newest = (
            select(Filing.message_id, Filing.topic_id, Filing.extra_id, Filing.filed_at)
            .ext(distinct_on(Filing.message_id))
            .where(Filing.mailbox_id == self._mailbox, Filing.filed_at >= since)
            .order_by(Filing.message_id, desc(Filing.filed_at), desc(Filing.list_version))
            .subquery()
        )
        async with self._sessions() as session:
            rows = await session.execute(
                select(newest.c.message_id, newest.c.topic_id, newest.c.extra_id).order_by(
                    desc(newest.c.filed_at), newest.c.message_id
                )
            )
            return [
                Filed(row.message_id, str(row.topic_id), None if row.extra_id is None else str(row.extra_id))
                for row in rows
            ]

    async def managed_labels(self) -> ResortLabels:
        """The managed labels of the latest list version, "Other" and the archive label with their stored ids."""
        return await read_managed_labels(self._sessions, self._mailbox)

    async def record_report(self, report: RefileReport) -> None:
        """Append the counts; the database sets the time."""
        async with self._sessions.begin() as session:
            await session.execute(
                select(
                    func.categories.record_refile_report(
                        self._mailbox, report.filed, report.checked, report.refiled, report.in_other, report.gone
                    )
                )
            )

    async def success_counts(self, since: datetime) -> SuccessCounts:
        """The counts behind the success numbers (D22): the newest filing of each mail, and the always-notify alerts.

        A mail whose rule was skipped (``sender_rule_not_applied``) was filed by the model, so it counts as such.
        """
        newest = (
            select(Filing.source, Filing.topic_id)
            .ext(distinct_on(Filing.message_id))
            .where(Filing.mailbox_id == self._mailbox, Filing.filed_at >= since)
            .order_by(Filing.message_id, desc(Filing.filed_at), desc(Filing.list_version))
            .subquery()
        )
        by_rule = func.count().filter(newest.c.source == "sender_rule")
        in_other = func.count().filter(newest.c.topic_id == uuid.UUID(OTHER_ID))
        always_notify = (
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.created_at >= since,
                text("exists (select 1 from jsonb_array_elements_text(alert.causes) c where c like 'always_notify:%')"),
            )
            .scalar_subquery()
        )
        async with self._sessions() as session:
            row = (
                await session.execute(select(func.count(), by_rule, in_other, always_notify).select_from(newest))
            ).one()
        filed, ruled, other, alerts = row
        applied, moved_back = await self._system_moves(since)
        return SuccessCounts(
            days=PERIOD.days,
            filed=filed,
            by_rule=ruled,
            by_model=filed - ruled,
            in_other=other,
            always_notify_alerts=alerts,
            system_applied=applied,
            system_moved_back=moved_back,
        )

    async def _system_moves(self, since: datetime) -> tuple[int, int]:
        """Items applied from automatic plans since ``since`` and how many of them a move back restored.

        An automatic plan approves every item itself (``decision_source`` threshold), and its items go when it is
        applied, so the plan's own kind identifies them; the plan is kept 14 days after it ended, the length of the
        period. A restore row names the same plan and mail as the apply row it undoes, so it is matched by both.
        """
        applied = (
            select(ApplyAudit.plan_id, ApplyAudit.message_id)
            .join(Plan, and_(Plan.mailbox_id == ApplyAudit.mailbox_id, Plan.id == ApplyAudit.plan_id))
            .where(
                ApplyAudit.mailbox_id == self._mailbox,
                ApplyAudit.kind == "apply",
                ApplyAudit.at >= since,
                Plan.kind == PlanKind.AUTO.value,
            )
            .subquery()
        )
        restored = (
            select(ApplyAudit.id)
            .where(
                ApplyAudit.mailbox_id == self._mailbox,
                ApplyAudit.kind == "restore",
                ApplyAudit.plan_id == applied.c.plan_id,
                ApplyAudit.message_id == applied.c.message_id,
            )
            .exists()
        )
        async with self._sessions() as session:
            row = (
                await session.execute(select(func.count(), func.count().filter(restored)).select_from(applied))
            ).one()
        return int(row[0]), int(row[1])
