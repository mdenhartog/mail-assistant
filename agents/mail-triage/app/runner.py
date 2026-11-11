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
        store: PurgePort,
        inbox: InboxPort,
        router: RouterPort,
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
        self._store = store
        self._inbox = inbox
        self._router = router
        self._heartbeat = heartbeat
        self._interval = interval_seconds
        self._now = now
        self._purged_on: date | None = None
        self._failed: dict[int, int] = {}

    async def mail_cycle(self) -> None:
        """Announce web changes, release due alerts, read new mail, catch up, send alerts and the overview, purge, beat.

        The web notice goes first and takes no part in quiet hours: a change from someone else must reach Marco soon.
        """
        await self._guard("web_notice", self._web_notice.run(self._now()))
        await self._guard("release_due", self._snooze.release_due())
        await self._guard("pipeline", self._pipeline.run_once())
        await self._guard("catchup", self._catchup.run_once())  # after new mail, so new mail always comes first
        await self._guard("deliver", self._delivery.deliver_open_alerts())
        await self._guard("overview", self._overview.send_overview())
        await self._guard("purge", self._purge())
        self._heartbeat.touch()

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
