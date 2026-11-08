"""The run loop: one mail cycle and one Telegram cycle that keep going when a step fails (spec AC-12, AC-27)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.adapters.telegram_inbox import Command
from app.runner import FailureNotice, Runner
from app.usecases.triage import RunSummary

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


class Steps:
    """Records the order of calls; named steps can be made to fail."""

    def __init__(self, *, failing: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.failing = failing or set()

    async def step(self, name: str) -> None:
        self.calls.append(name)
        if name in self.failing:
            raise RuntimeError(f"{name} broke with mail text: very private")


class Pipeline:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def run_once(self) -> RunSummary:
        await self.steps.step("pipeline")
        return RunSummary()


class Delivery:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def deliver_open_alerts(self) -> None:
        await self.steps.step("deliver")


class Snooze:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def release_due(self) -> list[str]:
        await self.steps.step("release_due")
        return []


class Overview:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def send_overview(self) -> None:
        await self.steps.step("overview")


class Store:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.purged: list[datetime] = []

    async def purge_content(self, before: datetime) -> int:
        await self.steps.step("purge")
        self.purged.append(before)
        return 0


class Inbox:
    def __init__(self, batches: list[list[Command]]) -> None:
        self.batches = batches

    async def poll_once(self) -> list[Command]:
        return self.batches.pop(0) if self.batches else []


class Router:
    def __init__(self, *, fail: bool = False) -> None:
        self.handled: list[Command] = []
        self.fail = fail

    async def handle(self, command: Command) -> None:
        self.handled.append(command)
        if self.fail:
            raise RuntimeError("boom")


def runner(
    steps: Steps,
    tmp_path: Path,
    *,
    inbox: Inbox | None = None,
    router: Router | None = None,
    now: datetime = NOW,
) -> tuple[Runner, Store]:
    store = Store(steps)
    return (
        Runner(
            pipeline=Pipeline(steps),
            delivery=Delivery(steps),
            snooze=Snooze(steps),
            overview=Overview(steps),
            store=store,
            inbox=inbox or Inbox([]),
            router=router or Router(),
            heartbeat=tmp_path / "heartbeat",
            interval_seconds=0.01,
            now=lambda: now,
        ),
        store,
    )


async def test_given_a_cycle_when_run_then_due_alerts_are_released_before_mail_is_read_and_alerts_are_sent(
    tmp_path: Path,
) -> None:
    steps = Steps()
    run, _ = runner(steps, tmp_path)

    await run.mail_cycle()

    assert steps.calls == ["release_due", "pipeline", "deliver", "overview", "purge"]


async def test_given_a_cycle_when_it_ends_then_the_heartbeat_file_is_touched(tmp_path: Path) -> None:
    run, _ = runner(Steps(), tmp_path)

    await run.mail_cycle()

    assert (tmp_path / "heartbeat").exists()


async def test_given_a_failing_step_when_a_cycle_runs_then_the_others_still_run_and_the_log_has_no_mail_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    steps = Steps(failing={"pipeline"})
    run, _ = runner(steps, tmp_path)

    await run.mail_cycle()

    assert steps.calls == ["release_due", "pipeline", "deliver", "overview", "purge"]
    assert "very private" not in caplog.text
    assert "RuntimeError" in caplog.text


async def test_given_two_cycles_on_the_same_day_when_run_then_old_content_is_purged_once_after_30_days(
    tmp_path: Path,
) -> None:
    steps = Steps()
    run, store = runner(steps, tmp_path)

    await run.mail_cycle()
    await run.mail_cycle()

    assert steps.calls.count("purge") == 1
    assert store.purged == [NOW - timedelta(days=30)]


async def test_given_commands_from_marco_when_the_telegram_cycle_runs_then_each_is_routed(tmp_path: Path) -> None:
    commands = [Command("text", "3", 1, 1, None), Command("button", "stop:1", 1, 2, "cb")]
    router = Router()
    run, _ = runner(Steps(), tmp_path, inbox=Inbox([commands]), router=router)

    await run.telegram_cycle()

    assert router.handled == commands


async def test_given_a_command_that_fails_when_routed_then_the_next_one_still_runs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    commands = [Command("text", "secret words", 1, 1, None), Command("text", "more", 1, 2, None)]
    router = Router(fail=True)
    run, _ = runner(Steps(), tmp_path, inbox=Inbox([commands]), router=router)

    await run.telegram_cycle()

    assert len(router.handled) == 2
    assert "secret words" not in caplog.text


async def test_given_a_stop_signal_when_running_then_both_loops_end(tmp_path: Path) -> None:
    steps = Steps()
    run, _ = runner(steps, tmp_path)
    stop = asyncio.Event()

    task = asyncio.create_task(run.run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, 2)

    assert steps.calls.count("pipeline") >= 1


async def test_given_a_given_up_mail_when_noticed_then_marco_gets_one_plain_message() -> None:
    said: list[str] = []

    class Chat:
        async def say(self, text: str) -> None:
            said.append(text)

    await FailureNotice(Chat()).notify_failure("abc123")

    assert len(said) == 1
    assert "abc123" in said[0]
    assert "inbox" in said[0]
