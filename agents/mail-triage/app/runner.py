"""The run loop: a mail cycle every poll interval and a Telegram cycle that listens continuously.

A step that fails is logged by type only (never its message, which could hold mail text) and the cycle goes on, so one
broken part never stops the others (spec AC-12, AC-27). The heartbeat file is touched at the end of every mail cycle;
the container probe fails when it gets too old.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import date, datetime
    from pathlib import Path

    from app.adapters.telegram_inbox import Command
    from app.usecases.triage import RunSummary

logger = logging.getLogger(__name__)

RETENTION = timedelta(days=30)  # ADR-0020
MAX_COMMAND_ATTEMPTS = 3  # a command that fails this often is given up, so one bad update cannot block the rest


class PipelinePort(Protocol):
    """Reads, judges and files new mail."""

    async def run_once(self) -> RunSummary:
        """One run."""
        ...


class CatchUpPort(Protocol):
    """Files the unread mail that was already in the inbox, once (INT-003)."""

    async def run_once(self) -> RunSummary:
        """One run."""
        ...


class ListSyncPort(Protocol):
    """Keeps Gmail in step with the category list (INT-004)."""

    async def run(self) -> object:
        """One pass."""
        ...


class ListNoticePort(Protocol):
    """Announces changes of the category list in Telegram (INT-004, ADR-0033, ADR-0046)."""

    async def run(self, now: datetime) -> None:
        """Send one notice for every list change not yet announced."""
        ...


class ResortStepPort(Protocol):
    """The plan build, the apply and the move back (INT-004, ADR-0046): one pass each."""

    async def run_once(self) -> object:
        """One pass."""
        ...


class RefileReportPort(Protocol):
    """The daily report on re-filed mail and mail in "Other" (INT-004, AC-46)."""

    async def run_once(self) -> object:
        """One report."""
        ...


class ApprovalNoticePort(Protocol):
    """Announces delayed plans in Telegram (INT-004, ADR-0046)."""

    async def run(self, now: datetime) -> None:
        """Send one notice for every scheduled plan not announced yet."""
        ...


class DeliveryPort(Protocol):
    """Sends alerts."""

    async def deliver_open_alerts(self) -> None:
        """Send what is open and unsent."""
        ...


class SnoozePort(Protocol):
    """Reopens snoozed alerts."""

    async def release_due(self) -> list[str]:
        """Release the due ones."""
        ...


class OverviewPort(Protocol):
    """Sends the daily overview."""

    async def send_overview(self) -> None:
        """Send it when it is due."""
        ...


class WebNoticePort(Protocol):
    """Announces changes made on the web (INT-002, ADR-0033)."""

    async def run(self, now: datetime) -> None:
        """Send a notice for every web change not yet announced."""
        ...


class CodeAlertPort(Protocol):
    """Warns about repeated wrong sign-in codes on the web (INT-002, ADR-0039)."""

    async def run(self, now: datetime) -> None:
        """Send one notice when five wrong or expired codes came in ten minutes."""
        ...


class PurgePort(Protocol):
    """Clears old mail content."""

    async def purge_content(self, before: datetime) -> int:
        """Clear content older than ``before``."""
        ...


class InboxPort(Protocol):
    """Telegram intake."""

    async def poll_once(self) -> list[Command]:
        """One long-poll."""
        ...

    def rewind(self, update_id: int) -> None:
        """Ask for this update again on the next poll."""
        ...


class RouterPort(Protocol):
    """Command routing."""

    async def handle(self, command: Command) -> None:
        """Run one command."""
        ...


class Say(Protocol):
    """A plain note to Marco."""

    async def say(self, text: str) -> None:
        """Send it."""
        ...


class FailureNotice:
    """The one error notice for a mail the agent gave up on (spec AC-27)."""

    def __init__(self, chat: Say) -> None:
        """Keep the chat."""
        self._chat = chat

    async def notify_failure(self, message_id: str) -> None:
        """Tell Marco; the mail itself stays untouched in the inbox."""
        await self._chat.say(
            f"I could not process the mail with id {message_id} after several tries. It stays in your inbox."
        )


class Runner:
    """Runs the cycles."""

    def __init__(  # noqa: PLR0913 - every part is injected for tests
        self,
        *,
        pipeline: PipelinePort,
        catchup: CatchUpPort,
        delivery: DeliveryPort,
        snooze: SnoozePort,
        overview: OverviewPort,
        web_notice: WebNoticePort,
        code_alert: CodeAlertPort,
        store: PurgePort,
        inbox: InboxPort,
        router: RouterPort,
        list_sync: ListSyncPort,
        list_notice: ListNoticePort,
        approval_notice: ApprovalNoticePort,
        resort_build: ResortStepPort,
        resort_apply: ResortStepPort,
        move_back: ResortStepPort,
        refile_report: RefileReportPort,
        refile_report_hour: int,
        list_sync_seconds: float,
        resort_apply_seconds: float,
        heartbeat: Path,
        interval_seconds: float,
        now: Callable[[], datetime],
    ) -> None:
        """Wire the parts, the heartbeat file, the poll interval and the clock."""
        self._pipeline = pipeline
        self._catchup = catchup
        self._delivery = delivery
        self._snooze = snooze
        self._overview = overview
        self._web_notice = web_notice
        self._code_alert = code_alert
        self._store = store
        self._inbox = inbox
        self._router = router
        self._list_sync = list_sync
        self._list_notice = list_notice
        self._approval_notice = approval_notice
        self._resort_build = resort_build
        self._resort_apply = resort_apply
        self._move_back = move_back
        self._refile_report = refile_report
        self._refile_hour = refile_report_hour
        self._refile_reported_on: date | None = None
        self._resort_apply_every = timedelta(seconds=resort_apply_seconds)
        self._resort_applied_at: datetime | None = None
        self._list_sync_every = timedelta(seconds=list_sync_seconds)
        self._list_synced_at: datetime | None = None
        self._heartbeat = heartbeat
        self._interval = interval_seconds
        self._now = now
        self._purged_on: date | None = None
        self._failed: dict[int, int] = {}

    async def mail_cycle(self) -> None:
        """Sync the category list, announce web changes, warn about wrong codes, release due alerts, read mail, ...

        The list sync goes first (when its cadence has passed) so that mail is never judged before version 1 exists.
        After it: catch up, send, purge, beat.
        The list notice, the web notice and the wrong-code alert go first and take no part in quiet hours: a change
        from someone else, or someone guessing codes, must reach Marco soon.
        """
        await self._guard("list_sync", self._sync_list())
        # A change of the list is announced like a web change: soon, outside quiet hours.
        await self._guard("list_notice", self._list_notice.run(self._now()))
        await self._guard("approval_notice", self._approval_notice.run(self._now()))
        await self._guard("web_notice", self._web_notice.run(self._now()))
        await self._guard("code_alert", self._code_alert.run(self._now()))
        await self._guard("release_due", self._snooze.release_due())
        await self._guard("pipeline", self._pipeline.run_once())
        await self._guard("catchup", self._catchup.run_once())  # after new mail, so new mail always comes first
        await self._guard("resort_build", self._resort_build.run_once())  # after the mail: new mail comes first
        await self._resort_steps()
        await self._guard("deliver", self._delivery.deliver_open_alerts())
        await self._guard("overview", self._overview.send_overview())
        await self._guard("refile_report", self._report_refiles())
        await self._guard("purge", self._purge())
        self._heartbeat.touch()

    async def _sync_list(self) -> None:
        now = self._now()
        if self._list_synced_at is not None and now - self._list_synced_at < self._list_sync_every:
            return
        self._list_synced_at = now  # also after a failure: the next cadence retries, a broken Gmail is not hammered
        await self._list_sync.run()

    async def _resort_steps(self) -> None:
        """The apply and the move back, when the apply poll has passed; a failure of one never stops the other."""
        now = self._now()
        if self._resort_applied_at is not None and now - self._resort_applied_at < self._resort_apply_every:
            return
        self._resort_applied_at = now
        await self._guard("resort_apply", self._resort_apply.run_once())
        await self._guard("move_back", self._move_back.run_once())

    async def _report_refiles(self) -> None:
        """Once per day, in the first cycle at or after the hour of the clock (UTC in production)."""
        now = self._now()
        if now.hour < self._refile_hour or self._refile_reported_on == now.date():
            return
        self._refile_reported_on = now.date()  # also after a failure: a broken Gmail is not hammered, tomorrow retries
        await self._refile_report.run_once()

    async def _purge(self) -> None:
        now = self._now()
        if self._purged_on != now.date():
            await self._store.purge_content(now - RETENTION)
            self._purged_on = now.date()

    @staticmethod
    async def _guard(name: str, step: Awaitable[object]) -> None:
        try:
            await step
        except Exception as error:
            logger.warning("step %s failed kind=%s", name, type(error).__name__)

    async def telegram_cycle(self) -> None:
        """Wait for Marco's commands and route each one, in order.

        A command that fails stops the batch and is asked for again: its id was not stored, and a later command must not
        move the stored id past it. After ``MAX_COMMAND_ATTEMPTS`` failures it is given up and the cycle goes on.
        """
        for command in await self._inbox.poll_once():
            try:
                await self._router.handle(command)
            except Exception as error:
                attempts = self._failed.get(command.update_id, 0) + 1
                self._failed = {command.update_id: attempts}  # only the latest failing update is remembered
                logger.warning("step command failed kind=%s attempt=%d", type(error).__name__, attempts)
                if attempts < MAX_COMMAND_ATTEMPTS:
                    self._inbox.rewind(command.update_id)
                    return

    async def run(self, stop: asyncio.Event) -> None:
        """Run both loops until ``stop`` is set."""
        await asyncio.gather(
            self._loop(stop, self.mail_cycle, self._interval), self._loop(stop, self.telegram_cycle, 0)
        )

    @staticmethod
    async def _loop(stop: asyncio.Event, cycle: Callable[[], Awaitable[None]], pause: float) -> None:
        while not stop.is_set():
            await cycle()
            try:
                await asyncio.wait_for(stop.wait(), timeout=pause or 0.001)
            except TimeoutError:
                continue
