"""U-mail-categories-23: the cycle announces list changes, and the list buttons reach their handler (AC-31, AC-48)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.telegram_inbox import Command
from app.runner import Runner
from app.settings import load_settings
from app.usecases.list_notice import ListNotice, ListNoticeActions
from app.wiring import build_runner
from tests.test_runner import (
    NOW,
    CatchUpStep,
    CodeAlertStep,
    Delivery,
    Inbox,
    ListSyncStep,
    Overview,
    Pipeline,
    Router,
    Snooze,
    Steps,
    Store,
    WebNoticeStep,
)
from tests.test_settings import VALID
from tests.usecases.test_dispatch import Rig, button

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    import pytest


class ListNoticeStep:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.ran_at: list[datetime] = []

    async def run(self, now: datetime) -> None:
        await self.steps.step("list_notice")
        self.ran_at.append(now)


def _runner(steps: Steps, tmp_path: Path, notice: ListNoticeStep) -> Runner:
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
        list_notice=notice,
        list_sync_seconds=60,
        heartbeat=tmp_path / "heartbeat",
        interval_seconds=0.01,
        now=lambda: NOW,
    )


async def test_given_a_cycle_when_it_runs_then_the_list_notice_runs_with_the_clock_before_the_web_notice(
    tmp_path: Path,
) -> None:
    steps = Steps()
    notice = ListNoticeStep(steps)
    run = _runner(steps, tmp_path, notice)

    await run.mail_cycle()

    assert notice.ran_at == [NOW]
    assert steps.calls[:2] == ["list_notice", "web_notice"]


async def test_given_the_list_notice_fails_when_a_cycle_runs_then_the_rest_goes_on_and_only_the_type_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    steps = Steps(failing={"list_notice"})
    run = _runner(steps, tmp_path, ListNoticeStep(steps))

    with caplog.at_level(logging.WARNING):
        await run.mail_cycle()

    assert "deliver" in steps.calls
    assert "step list_notice failed kind=RuntimeError" in caplog.text
    assert "very private" not in caplog.text


async def test_given_the_list_buttons_when_pressed_then_they_reach_the_list_actions_with_action_and_nonce() -> None:
    rig = Rig()
    seen: list[tuple[Command, str, str]] = []

    class Actions:
        async def on_button(self, command: Command, action: str, nonce: str) -> None:
            seen.append((command, action, nonce))

    router = rig.router()
    router.register_list_actions(Actions())  # type: ignore[arg-type]
    nonce = "A" * 22

    await router.handle(button(f"catundo:{nonce}"))
    await router.handle(button(f"catlock:{nonce}"))

    assert [(a, n) for _c, a, n in seen] == [("catundo", nonce), ("catlock", nonce)]
    assert rig.chat.acknowledged == ["cb1", "cb1"]


async def test_given_no_list_actions_or_a_malformed_button_when_pressed_then_nothing_happens() -> None:
    rig = Rig()
    seen: list[str] = []

    class Actions:
        async def on_button(self, command: Command, action: str, nonce: str) -> None:
            seen.append(action)

    await rig.router().handle(button(f"catundo:{'A' * 22}"))  # not registered
    router = rig.router()
    router.register_list_actions(Actions())  # type: ignore[arg-type]
    await router.handle(button("catundo:short"))
    await router.handle(button("catundo:" + "A" * 22 + ":x"))

    assert seen == []
    assert rig.chat.edited == []
    assert rig.chat.said == []


def _wired() -> Any:
    engine = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")  # never connected in this test
    return build_runner(
        load_settings(VALID),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(timeout=httpx.Timeout(5.0)),
        mailbox=object(),
        sender=object(),
        labels=object(),  # type: ignore[arg-type]
        own_address="marco@example.com",
        heartbeat=None,  # type: ignore[arg-type]
        now=lambda: NOW,
    )


def test_given_the_wiring_when_built_then_the_notice_and_its_buttons_are_set_for_the_allowed_chat() -> None:
    settings = load_settings(VALID)
    built = _wired()

    notice = built._list_notice
    actions = vars(built._router).get("_list")

    assert isinstance(notice, ListNotice)
    assert vars(notice)["_chat_id"] == settings.telegram_allowed_chat_id
    assert isinstance(actions, ListNoticeActions)
    assert vars(actions)["_chat_id"] == settings.telegram_allowed_chat_id
