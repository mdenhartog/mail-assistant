"""The database side of the daily re-file report (INT-004, AC-46, ADR-0043).

One store per mailbox: every statement filters on ``mailbox_id``. The agent role reads ``filing`` and ``category_label``
and writes the report only through ``categories.record_refile_report``; it has no right on the report table itself
(``app/db/grants.sql``). No statement here is built from a string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.db.models import CategoryLabel, Filing
from app.usecases.refile_report import Filed

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.usecases.refile_report import RefileReport

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
            select(Filing.message_id, Filing.topic_id, Filing.filed_at)
            .ext(distinct_on(Filing.message_id))
            .where(Filing.mailbox_id == self._mailbox, Filing.filed_at >= since)
            .order_by(Filing.message_id, desc(Filing.filed_at), desc(Filing.list_version))
            .subquery()
        )
        async with self._sessions() as session:
            rows = await session.execute(
                select(newest.c.message_id, newest.c.topic_id).order_by(desc(newest.c.filed_at), newest.c.message_id)
            )
            return [Filed(row.message_id, str(row.topic_id)) for row in rows]

    async def category_labels(self) -> dict[str, str]:
        """Category id to the Gmail label id recorded for it; the nil id of "Other" is in the map."""
        async with self._sessions() as session:
            rows = await session.execute(
                select(CategoryLabel.category_id, CategoryLabel.label_id).where(
                    CategoryLabel.mailbox_id == self._mailbox
                )
            )
            return {str(row.category_id): row.label_id for row in rows}

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
