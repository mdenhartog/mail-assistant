"""U-label-structure-24: the tips are written once, when the plan became ready, and never before (ADR-0056)."""

from __future__ import annotations

from app.usecases.resort_build import BuildStatus
from tests.resort_build_support import FINANCE, TRAVEL, Rig


async def test_given_a_plan_that_becomes_ready_then_the_tips_are_written_once_for_that_plan_and_list() -> None:
    rig = Rig()
    rig.request()
    rig.gmail.add_mail(("INBOX",), subject="a")
    rig.judge.answer = FINANCE

    result = await rig.build.run_once()

    assert result.status is BuildStatus.READY
    assert rig.tips.calls == [(rig.store.plan().plan_id, (FINANCE, TRAVEL))]


async def test_given_a_build_that_pauses_or_is_replaced_then_no_tips_are_written() -> None:
    rig = Rig(per_run=1)
    rig.request()
    rig.gmail.add_mail(("INBOX",), subject="a")
    rig.gmail.add_mail(("INBOX",), subject="b")

    result = await rig.build.run_once()

    assert result.status is BuildStatus.PAUSED
    assert rig.tips.calls == []


async def test_given_a_ready_plan_then_the_notice_is_sent_before_the_tips_are_written() -> None:
    rig = Rig()
    rig.request()
    rig.gmail.add_mail(("INBOX",), subject="a")

    await rig.build.run_once()

    assert rig.tips.seen_texts == [1]
