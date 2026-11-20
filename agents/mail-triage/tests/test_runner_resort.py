"""U-mail-categories-22, criteria 4 and 5 and open points (f), (3): the cycle runs the plan build, the apply and the
move back in that order, each guarded; the approval notice runs with the clock; the numbers come from the settings."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.runner import Runner
from app.settings import SettingsError, load_settings
from app.usecases.approval_notice import PlanNoticeActions
from app.usecases.resort_build import BuildResult, BuildStatus
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

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class Build:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def run_once(self) -> BuildResult:
        await self.steps.step("resort_build")
        return BuildResult(BuildStatus.IDLE)


class Apply:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def run_once(self) -> None:
        await self.steps.step("resort_apply")


class Back:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps

    async def run_once(self) -> None:
        await self.steps.step("move_back")


class Announce:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.ran_at: list[datetime] = []

    async def run(self, now: datetime) -> None:
        await self.steps.step("approval_notice")
        self.ran_at.append(now)


def _runner(
    steps: Steps, tmp_path: Path, clock: Clock, *, poll: float = 60, announce: Announce | None = None
) -> Runner:
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
        approval_notice=announce or Announce(steps),
        resort_build=Build(steps),
        resort_apply=Apply(steps),
        move_back=Back(steps),
        list_sync_seconds=60,
        refile_report=ResortIdle(),
        refile_report_hour=6,
        resort_apply_seconds=poll,
        heartbeat=tmp_path / "heartbeat",
        interval_seconds=0.01,
        now=clock,
    )


async def test_given_a_cycle_when_it_runs_then_build_apply_and_move_back_run_in_that_order_after_the_mail(
    tmp_path: Path,
) -> None:
    steps = Steps()

    await _runner(steps, tmp_path, Clock()).mail_cycle()

    calls = steps.calls
    assert calls.index("catchup") < calls.index("resort_build") < calls.index("resort_apply")
    assert calls.index("resort_apply") < calls.index("move_back") < calls.index("deliver")


async def test_given_a_cycle_when_it_runs_then_the_approval_notice_runs_with_the_clock_before_the_web_notice(
    tmp_path: Path,
) -> None:
    steps = Steps()
    announce = Announce(steps)

    await _runner(steps, tmp_path, Clock(), announce=announce).mail_cycle()

    assert announce.ran_at == [NOW]
    assert steps.calls.index("approval_notice") < steps.calls.index("web_notice")


@pytest.mark.parametrize("broken", ["resort_build", "resort_apply", "move_back", "approval_notice"])
async def test_given_one_step_fails_when_a_cycle_runs_then_the_others_go_on_and_only_the_type_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, broken: str
) -> None:
    steps = Steps(failing={broken})

    with caplog.at_level(logging.WARNING):
        await _runner(steps, tmp_path, Clock()).mail_cycle()

    assert {"resort_build", "resort_apply", "move_back", "approval_notice", "deliver"} <= set(steps.calls)
    assert f"step {broken} failed kind=RuntimeError" in caplog.text
    assert "very private" not in caplog.text


async def test_given_the_apply_poll_when_cycles_follow_each_other_then_the_apply_waits_and_the_build_does_not(
    tmp_path: Path,
) -> None:
    steps, clock = Steps(), Clock()
    run = _runner(steps, tmp_path, clock, poll=120)

    await run.mail_cycle()
    clock.now += timedelta(seconds=60)
    await run.mail_cycle()
    clock.now += timedelta(seconds=60)
    await run.mail_cycle()

    assert steps.calls.count("resort_build") == 3
    assert steps.calls.count("resort_apply") == 2  # at 0 s and at 120 s
    assert steps.calls.count("move_back") == 2


def test_given_the_settings_when_they_are_loaded_then_the_resort_numbers_have_defaults_and_can_be_set() -> None:
    default = load_settings(VALID)
    assert (default.plan_debounce_minutes, default.plan_cap, default.apply_poll_seconds) == (10, 5000, 60)
    assert (default.apply_threshold, default.apply_delay_minutes) == (50, 15)

    custom = load_settings(
        VALID
        | {
            "PLAN_DEBOUNCE_MINUTES": "3",
            "PLAN_CAP": "7",
            "APPLY_POLL_SECONDS": "5",
            "APPLY_THRESHOLD": "9",
            "APPLY_DELAY_MINUTES": "0",
        }
    )
    assert (custom.plan_debounce_minutes, custom.plan_cap, custom.apply_poll_seconds) == (3, 7, 5)
    assert (custom.apply_threshold, custom.apply_delay_minutes) == (9, 0)


@pytest.mark.parametrize("key", ["PLAN_DEBOUNCE_MINUTES", "PLAN_CAP", "APPLY_POLL_SECONDS", "APPLY_THRESHOLD"])
def test_given_a_resort_number_below_one_when_settings_load_then_the_key_is_named(key: str) -> None:
    with pytest.raises(SettingsError, match=key):
        load_settings(VALID | {key: "0"})


def _wired(extra: dict[str, str] | None = None) -> Any:
    engine = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")  # never connected in this test
    return build_runner(
        load_settings(VALID | (extra or {})),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(timeout=httpx.Timeout(5.0)),
        mailbox=object(),
        sender=object(),
        labels=object(),  # type: ignore[arg-type]
        build_mailbox=object(),  # type: ignore[arg-type]
        apply_mailbox=object(),  # type: ignore[arg-type]
        own_address="marco@example.com",
        heartbeat=None,  # type: ignore[arg-type]
        now=lambda: NOW,
    )


def test_given_the_wiring_when_built_then_the_debounce_the_cap_and_the_apply_poll_come_from_the_settings() -> None:
    built = _wired({"PLAN_DEBOUNCE_MINUTES": "3", "PLAN_CAP": "7", "APPLY_POLL_SECONDS": "5"})

    build = vars(built)["_resort_build"]
    assert vars(build)["_debounce"] == timedelta(minutes=3)
    assert vars(build)["_cap"] == 7
    assert vars(built)["_resort_apply_every"] == timedelta(seconds=5)


def test_given_the_wiring_when_built_then_the_plan_buttons_are_registered_for_the_allowed_chat() -> None:
    built = _wired()

    actions = vars(vars(built)["_router"]).get("_plan")

    assert isinstance(actions, PlanNoticeActions)
    assert vars(actions)["_chat_id"] == load_settings(VALID).telegram_allowed_chat_id
