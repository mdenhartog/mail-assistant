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


class CatchUpStep:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def run_once(self) -> RunSummary:
        await self.steps.step("catchup")
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


class WebNoticeStep:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.ran_at: list[datetime] = []

    async def run(self, now: datetime) -> None:
        await self.steps.step("web_notice")
        self.ran_at.append(now)


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
        self.rewound: list[int] = []

    async def poll_once(self) -> list[Command]:
        return self.batches.pop(0) if self.batches else []

    def rewind(self, update_id: int) -> None:
        self.rewound.append(update_id)


class Router:
    def __init__(self, *, fail: bool = False) -> None:
        self.handled: list[Command] = []
        self.fail = fail

    async def handle(self, command: Command) -> None:
        self.handled.append(command)
        if self.fail:
            raise RuntimeError("boom")


def runner(  # noqa: PLR0913 - every part of the runner is a keyword here
    steps: Steps,
    tmp_path: Path,
    *,
    inbox: Inbox | None = None,
    router: Router | None = None,
    now: datetime = NOW,
    web_notice: WebNoticeStep | None = None,
) -> tuple[Runner, Store]:
    store = Store(steps)
    web_notice = web_notice or WebNoticeStep(steps)
    return (
        Runner(
            pipeline=Pipeline(steps),
            catchup=CatchUpStep(steps),
            delivery=Delivery(steps),
            snooze=Snooze(steps),
            overview=Overview(steps),
            web_notice=web_notice,
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

    assert steps.calls == ["web_notice", "release_due", "pipeline", "catchup", "deliver", "overview", "purge"]


async def test_given_a_cycle_when_run_then_web_changes_are_announced_first_with_the_clock_of_the_runner(
    tmp_path: Path,
) -> None:
    steps = Steps()
    web_notice = WebNoticeStep(steps)
    run, _ = runner(steps, tmp_path, web_notice=web_notice)

    await run.mail_cycle()

    assert steps.calls[0] == "web_notice"
    assert web_notice.ran_at == [NOW]


async def test_given_a_failing_web_notice_when_a_cycle_runs_then_the_mail_steps_still_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    steps = Steps(failing={"web_notice"})
    run, _ = runner(steps, tmp_path)

    await run.mail_cycle()

    assert steps.calls[1:] == ["release_due", "pipeline", "catchup", "deliver", "overview", "purge"]
    assert "step web_notice failed kind=RuntimeError" in caplog.text
    assert "very private" not in caplog.text


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

    assert steps.calls == ["web_notice", "release_due", "pipeline", "catchup", "deliver", "overview", "purge"]
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
    commands = [Command("text", "3", 1, 1, None, 1), Command("button", "stop:1", 1, 2, "cb", 2)]
    router = Router()
    run, _ = runner(Steps(), tmp_path, inbox=Inbox([commands]), router=router)

    await run.telegram_cycle()

    assert router.handled == commands


async def test_given_a_command_that_fails_when_routed_then_the_rest_of_the_batch_waits_and_the_log_has_no_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    commands = [Command("text", "secret words", 1, 1, None, 1), Command("text", "more", 1, 2, None, 2)]
    router = Router(fail=True)
    inbox = Inbox([commands])
    run, _ = runner(Steps(), tmp_path, inbox=inbox, router=router)

    await run.telegram_cycle()

    assert [c.update_id for c in router.handled] == [1]  # a later update must not move the stored id past it
    assert inbox.rewound == [1]  # the failed update is asked for again, not lost
    assert "secret words" not in caplog.text


async def test_given_an_update_that_keeps_failing_when_it_has_failed_three_times_then_it_is_not_asked_for_again(
    tmp_path: Path,
) -> None:
    command = Command("text", "x", 1, 1, None, 1)
    router = Router(fail=True)
    inbox = Inbox([[command]] * 5)
    run, _ = runner(Steps(), tmp_path, inbox=inbox, router=router)

    for _ in range(5):
        await run.telegram_cycle()

    assert inbox.rewound == [1, 1]  # tried three times in all, then the cycle goes on past it


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


async def test_given_the_catch_up_fails_when_a_cycle_runs_then_the_later_steps_and_the_heartbeat_still_happen(
    tmp_path: Path,
) -> None:
    steps = Steps(failing={"catchup"})
    run, _ = runner(steps, tmp_path)

    await run.mail_cycle()

    assert steps.calls == ["web_notice", "release_due", "pipeline", "catchup", "deliver", "overview", "purge"]
    assert (tmp_path / "heartbeat").exists()


async def test_given_the_pipeline_fails_when_a_cycle_runs_then_the_catch_up_still_runs(tmp_path: Path) -> None:
    steps = Steps(failing={"pipeline"})
    run, _ = runner(steps, tmp_path)

    await run.mail_cycle()

    assert steps.calls.index("catchup") > steps.calls.index("pipeline")
