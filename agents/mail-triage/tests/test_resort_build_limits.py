"""U-mail-categories-14, criteria 3, 4, 5: cap, budget and debounce (AC-11, AC-33)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from app.core.resort_plan import PlanState
from app.usecases.resort_build import PLAN_CAP, BuildStatus
from tests.fakes.seeds import SCOPE_MAILS, seed_scope_mails
from tests.resort_build_support import RESERVE, TRAVEL, Rig


async def test_the_newest_5000_are_in_the_plan_and_the_rest_is_not_looked_at() -> None:
    rig = Rig(daily_total=RESERVE + 2 * SCOPE_MAILS + 10)
    rig.request()
    ids = seed_scope_mails(rig.gmail, SCOPE_MAILS)
    rig.judge.answer = TRAVEL

    result = await rig.build.run_once()

    plan = rig.store.plan()
    assert PLAN_CAP == 5000
    assert result.status is BuildStatus.READY
    assert plan.checked == 5000
    assert result.numbers is not None
    assert result.numbers.not_looked_at == 1
    assert ids[0] not in {i.message_id for i in rig.store.items_of(plan)}  # the oldest is the one left out
    assert ids[-1] in {i.message_id for i in rig.store.items_of(plan)}
    assert "1 not looked at" in rig.telegram.texts[0]
    assert rig.store.not_looked_at[plan.plan_id] == 1
    assert rig.store.estimates[plan.plan_id] == SCOPE_MAILS


async def test_zero_budget_never_uses_the_reserve_and_the_build_continues_the_next_day() -> None:
    rig = Rig(daily_total=RESERVE + 6)  # room for three mails above the reserve
    rig.request()
    for n in range(5):
        rig.gmail.add_mail(("INBOX",), subject=f"s{n}")
    rig.judge.answer = TRAVEL

    first = await rig.build.run_once()

    assert first.status is BuildStatus.PAUSED
    assert rig.store.plan().state is PlanState.BUILDING
    assert rig.store.plan().checked == 3
    assert rig.ledger.available() == 0
    assert rig.ledger.spend_reserve(RESERVE)  # the whole reserve is still there
    again = await rig.build.run_once()
    assert again.status is BuildStatus.PAUSED
    assert rig.store.plan().checked == 3
    assert rig.telegram.texts == []

    rig.clock.advance(timedelta(days=1))
    done = await rig.build.run_once()

    assert done.status is BuildStatus.READY
    assert rig.store.plan().checked == 5
    assert len(rig.store.items_of(rig.store.plan())) == 5  # no mail judged twice, none skipped


async def test_a_list_change_builds_no_plan_even_when_the_debounce_time_has_passed() -> None:
    rig = Rig()
    rig.gmail.add_mail(("INBOX",), subject="a")
    for _ in range(3):  # saved by hand, by upload or by Undo: all are a new list version
        rig.store.save_list()
        rig.clock.advance(timedelta(hours=1))
        assert (await rig.build.run_once()).status is BuildStatus.IDLE
    assert rig.store.plans == []
    assert rig.judge.calls == 0
    assert not [c for c in rig.gmail.calls if "modify" in c]  # no mail moves


async def test_a_newer_list_cancels_the_build_without_half_written_items() -> None:
    rig = Rig(daily_total=RESERVE + 4)
    rig.request()
    for n in range(4):
        rig.gmail.add_mail(("INBOX", rig.finance_label), subject=f"s{n}")
    rig.judge.answer = TRAVEL
    await rig.build.run_once()  # two mails judged, then the budget is gone
    assert rig.store.plan().state is PlanState.BUILDING
    assert rig.store.plan().auto_items == 2  # the default threshold of 50 sends them to the auto plan
    old = rig.store.plan()

    rig.store.save_list()
    rig.clock.advance(timedelta(days=1, minutes=11))
    await rig.build.run_once()  # the outdated plan is replaced and no new one starts

    replaced = next(p for p in rig.store.plans if p.plan_id == old.plan_id)
    assert replaced.state is PlanState.REPLACED
    assert rig.store.items_of(replaced) == []
    assert rig.store.plans == [replaced]


async def test_a_list_saved_during_the_build_stops_it_before_another_mail_is_judged() -> None:
    rig = Rig()
    rig.request()
    for n in range(5):
        rig.gmail.add_mail(("INBOX", rig.finance_label), subject=f"s{n}")
    rig.judge.answer = TRAVEL
    rig.judge.on_judge = rig.store.save_list

    result = await rig.build.run_once()

    assert result.status is BuildStatus.CANCELLED
    assert rig.judge.calls == 1
    assert rig.store.plan().state is PlanState.REPLACED
    assert rig.store.items_of(rig.store.plan()) == []
    assert rig.telegram.texts == []


async def test_a_plan_that_is_scheduled_or_applying_is_left_alone_when_the_list_changes() -> None:
    for state in (PlanState.SCHEDULED, PlanState.APPLYING):
        rig = Rig()
        rig.request()
        rig.gmail.add_mail(("INBOX",), subject="a")
        await rig.build.run_once()
        rig.store.plans[-1] = replace(rig.store.plan(), state=state)
        rig.store.save_list()
        rig.clock.advance(timedelta(hours=1))

        assert (await rig.build.run_once()).status is BuildStatus.IDLE
        assert [p.state for p in rig.store.plans] == [state]  # not replaced, no new plan
