"""U-mail-categories-25, criterion 2 and the open points on settings and wiring (AC-46): the daily re-file report.

The runner runs the report once per day, at or after a configured hour of the injected clock, guarded like the other
steps: a failure is logged by its exception type only and the cycle goes on.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.scope import ArchiveLabel
from app.runner import Runner
from app.settings import SettingsError, load_settings
from app.wiring import build_runner
from tests.test_runner import (
    CatchUpStep,
    CodeAlertStep,
    Delivery,
    Inbox,
    ListNoticeIdle,
    ListSyncStep,
    Overview,
    Pipeline,
    ResortIdle,
    Router,
    Snooze,
    Steps,
    Store,
    WebNoticeStep,
)
from tests.test_settings import VALID

if TYPE_CHECKING:
    from pathlib import Path

HOUR = 6
MORNING = datetime(2026, 12, 1, HOUR, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Report:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def run_once(self) -> None:
        await self.steps.step("refile_report")


def _runner(steps: Steps, tmp_path: Path, clock: Clock, hour: int = HOUR) -> Runner:
    return Runner(
        pipeline=Pipeline(steps),
        catchup=CatchUpStep(steps),
        delivery=Delivery(steps),
        snooze=Snooze(steps),
        overview=Overview(steps),
        web_notice=WebNoticeStep(steps),
        code_alert=CodeAlertStep(steps),
        store=Store(steps),
        inbox=Inbox([]),
        router=Router(),
        list_sync=ListSyncStep(),
        list_notice=ListNoticeIdle(),
        approval_notice=ResortIdle(),
        resort_build=ResortIdle(),
        resort_apply=ResortIdle(),
        move_back=ResortIdle(),
        refile_report=Report(steps),
        refile_report_hour=hour,
        list_sync_seconds=60,
        resort_apply_seconds=60,
        heartbeat=tmp_path / "heartbeat",
        interval_seconds=0.01,
        now=clock,
    )


async def test_given_two_cycles_in_one_day_when_they_run_after_the_hour_then_the_report_runs_once(
    tmp_path: Path,
) -> None:
    steps, clock = Steps(), Clock(MORNING)
    run = _runner(steps, tmp_path, clock)

    await run.mail_cycle()
    clock.now += timedelta(hours=10)
    await run.mail_cycle()

    assert steps.calls.count("refile_report") == 1


async def test_given_a_cycle_before_the_hour_when_it_runs_then_the_report_waits_for_the_hour(tmp_path: Path) -> None:
    steps, clock = Steps(), Clock(MORNING - timedelta(minutes=1))
    run = _runner(steps, tmp_path, clock)

    await run.mail_cycle()
    assert "refile_report" not in steps.calls

    clock.now = MORNING
    await run.mail_cycle()
    assert steps.calls.count("refile_report") == 1


async def test_given_the_next_day_when_a_cycle_runs_after_the_hour_then_the_report_runs_again(tmp_path: Path) -> None:
    steps, clock = Steps(), Clock(MORNING)
    run = _runner(steps, tmp_path, clock)

    await run.mail_cycle()
    clock.now += timedelta(days=1)
    await run.mail_cycle()

    assert steps.calls.count("refile_report") == 2


async def test_given_a_restart_late_in_the_day_when_the_first_cycle_runs_then_the_report_runs_that_day(
    tmp_path: Path,
) -> None:
    steps = Steps()

    await _runner(steps, tmp_path, Clock(MORNING + timedelta(hours=14))).mail_cycle()

    assert steps.calls.count("refile_report") == 1


async def test_given_the_report_fails_when_a_cycle_runs_then_the_others_go_on_and_only_the_type_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    steps, clock = Steps(failing={"refile_report"}), Clock(MORNING)
    run = _runner(steps, tmp_path, clock)

    with caplog.at_level(logging.WARNING):
        await run.mail_cycle()
        clock.now += timedelta(minutes=1)
        await run.mail_cycle()

    assert "deliver" in steps.calls
    assert "step refile_report failed kind=RuntimeError" in caplog.text
    assert "very private" not in caplog.text
    assert steps.calls.count("refile_report") == 1  # a broken Gmail is not hammered: the next day tries again


def test_given_the_settings_when_loaded_then_the_report_hour_and_cap_have_defaults_and_can_be_set() -> None:
    default = load_settings(VALID)
    assert (default.refile_report_hour, default.refile_report_cap) == (6, 500)

    custom = load_settings(VALID | {"REFILE_REPORT_HOUR": "23", "REFILE_REPORT_CAP": "40"})
    assert (custom.refile_report_hour, custom.refile_report_cap) == (23, 40)


@pytest.mark.parametrize(
    ("key", "value"), [("REFILE_REPORT_HOUR", "24"), ("REFILE_REPORT_HOUR", "-1"), ("REFILE_REPORT_CAP", "0")]
)
def test_given_a_report_number_out_of_range_when_settings_load_then_the_key_is_named(key: str, value: str) -> None:
    with pytest.raises(SettingsError, match=key):
        load_settings(VALID | {key: value})


def test_given_the_wiring_when_built_then_the_report_hour_cap_and_gmail_come_from_settings_and_apply_adapter() -> None:
    engine = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")  # never connected in this test
    apply_mailbox: Any = object()
    built = build_runner(
        load_settings(VALID | {"REFILE_REPORT_HOUR": "3", "REFILE_REPORT_CAP": "40"}),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(timeout=httpx.Timeout(5.0)),
        mailbox=object(),
        sender=object(),
        labels=object(),  # type: ignore[arg-type]
        build_mailbox=object(),  # type: ignore[arg-type]
        apply_mailbox=apply_mailbox,
        archive=ArchiveLabel("Archive"),
        own_address="marco@example.com",
        heartbeat=None,  # type: ignore[arg-type]
        now=lambda: MORNING,
    )

    report = vars(built)["_refile_report"]
    assert vars(built)["_refile_hour"] == 3
    assert vars(report)["_max_checked"] == 40
    assert vars(report)["_mailbox"] is apply_mailbox
