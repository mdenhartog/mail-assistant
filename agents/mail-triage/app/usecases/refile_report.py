"""The daily report for AC-46: how much the user re-filed by hand and how much of the new mail sits in "Other".

It compares the label recorded in ``filing`` with the label the mail carries now. Gmail history is not used (it does not
say who changed a label). The report holds counts only: no sender, no subject, no message id (AC-30). Pinned mail has no
``filing`` row (ADR-0048), so Google security mail and the sign-in code mail never enter these numbers. The one-year
retention of ``filing`` is the database's ``purge_expired()``, not this report.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from app.core.judgement import OTHER_LABEL
from app.core.scope import LABEL_PREFIX

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail

__all__ = ["PERIOD", "Filed", "RefileMailbox", "RefileReport", "RefileReportService", "RefileStore"]

logger = logging.getLogger(__name__)

PERIOD = timedelta(days=14)  # the AC-46 horizon: two weeks after R1


@dataclass(frozen=True, slots=True)
class Filed:
    """The newest ``filing`` row of one mail: its id and the category it was filed under."""

    message_id: str
    category_id: str


@dataclass(frozen=True, slots=True)
class RefileReport:
    """The numbers of one run. ``gone`` mails count as checked but are neither re-filed nor in "Other".

    The shares are of the checked mails; when the cap is not reached, that is every mail filed in the period.
    """

    filed: int  # every mail filed in the period
    checked: int  # the mails looked at in Gmail: at most the cap, the newest first
    refiled: int
    in_other: int
    gone: int

    @property
    def refiled_percent(self) -> float:
        """Share of the checked mails the user re-filed by hand."""
        return 100.0 * self.refiled / self.checked if self.checked else 0.0

    @property
    def other_percent(self) -> float:
        """Share of the checked mails that sits under "Other" now."""
        return 100.0 * self.in_other / self.checked if self.checked else 0.0


class RefileStore(Protocol):
    """``filing``, the category labels and the report audit table."""

    async def filings_since(self, since: datetime) -> list[Filed]:
        """The newest filing of each mail filed since ``since``, the most recently filed first."""
        ...

    async def category_labels(self) -> dict[str, str]:
        """Category id to the Gmail label id recorded for it (``OTHER_ID`` included)."""
        ...

    async def record_report(self, report: RefileReport) -> None:
        """Append the counts to the audit table."""
        ...


class RefileMailbox(Protocol):
    """Gmail through the narrow adapter. Blocking calls; run in a thread."""

    def label_names(self) -> dict[str, str]:
        """Label id to label name."""
        ...

    def fetch(self, message_id: str) -> FetchedMail | None:
        """Label ids of one mail; ``None`` when it no longer exists."""
        ...


class RefileReportService:
    """Builds the report, writes it to the log and the audit table."""

    def __init__(
        self, store: RefileStore, mailbox: RefileMailbox, *, now: Callable[[], datetime], max_checked: int
    ) -> None:
        """Wire the store, Gmail, the clock and the most mails one run may fetch from Gmail."""
        self._store = store
        self._mailbox = mailbox
        self._now = now
        self._max_checked = max_checked

    async def run_once(self) -> RefileReport:
        """Compare every filing of the period with the mail's current label and record the counts."""
        filings = await self._store.filings_since(self._now() - PERIOD)
        recorded = await self._store.category_labels()
        names = await asyncio.to_thread(self._mailbox.label_names)
        other_ids = {label_id for label_id, name in names.items() if name == OTHER_LABEL}
        refiled = in_other = gone = 0
        checked = filings[: self._max_checked]  # the store hands the newest first
        for entry in checked:
            mail = await asyncio.to_thread(self._mailbox.fetch, entry.message_id)
            if mail is None:
                gone += 1
                continue
            held = {label_id for label_id in mail.labels if names.get(label_id, "").startswith(LABEL_PREFIX)}
            in_other += bool(held & other_ids)
            was = recorded.get(entry.category_id)
            refiled += was is not None and held != {was}  # a category without a label cannot be compared
        report = RefileReport(filed=len(filings), checked=len(checked), refiled=refiled, in_other=in_other, gone=gone)
        await self._store.record_report(report)
        logger.info(
            "refile report filed=%d checked=%d refiled=%d (%.1f%%) in_other=%d (%.1f%%) gone=%d",
            report.filed,
            report.checked,
            report.refiled,
            report.refiled_percent,
            report.in_other,
            report.other_percent,
            report.gone,
        )
        return report
