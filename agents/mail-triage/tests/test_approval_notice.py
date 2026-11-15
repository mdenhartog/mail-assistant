"""U-mail-categories-16: approvals wait in Telegram with Cancel and Lock; buttons are single use (AC-42, AC-48)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core import approval_text
from app.usecases.resort_apply import Offer
from tests.approval_notice_support import DELAY, NOW, OTHER_PLAN, PLAN, Rig, scheduled
from tests.list_notice_support import CHAT


async def test_given_an_approval_above_the_threshold_then_one_notice_with_cancel_and_lock_is_sent() -> None:
    rig = scheduled()

    await rig.notice.run(NOW)
    await rig.notice.run(NOW)

    assert len(rig.chat.sent) == 1
    message = rig.chat.sent[0]
    assert "60 mails move at 2026-11-14 09:15 UTC" in message.text
    assert [b.label for b in message.buttons] == [approval_text.CANCEL_LABEL, approval_text.LOCK_LABEL]
    assert [approval_text.split_button(b.data)[0] for b in message.buttons] == [  # type: ignore[index]
        approval_text.CANCEL,
        approval_text.LOCK,
    ]


async def test_given_no_scheduled_plan_when_the_notice_runs_then_nothing_is_sent() -> None:
    rig = Rig()
    rig.plans.states[PLAN] = "ready"

    await rig.notice.run(NOW)

    assert rig.chat.sent == []


async def test_given_a_failed_send_when_the_notice_runs_again_then_it_is_announced_then() -> None:
    rig = scheduled()
    rig.chat.fail_send = True
    with pytest.raises(RuntimeError):
        await rig.notice.run(NOW)
    rig.chat.fail_send = False

    await rig.notice.run(NOW)

    assert len(rig.chat.sent) == 1


async def test_given_cancel_before_apply_after_then_the_plan_is_cancelled_and_nothing_moves() -> None:
    rig = scheduled()
    await rig.notice.run(NOW)

    rig.clock[0] = NOW + timedelta(minutes=5)
    await rig.press(rig.data(0))

    assert rig.plans.states[PLAN] == "cancelled"
    assert rig.chat.edits == [(7, approval_text.CANCELLED)]
    assert not rig.lock.locked


async def test_given_cancel_after_the_delay_expired_then_it_is_refused_and_the_notice_says_so() -> None:
    rig = scheduled()
    await rig.notice.run(NOW)

    rig.clock[0] = NOW + DELAY
    await rig.press(rig.data(0))

    assert rig.plans.states[PLAN] == "scheduled"
    assert rig.chat.edits == [(7, approval_text.TOO_LATE)]


async def test_given_the_plan_is_no_longer_scheduled_when_cancel_is_pressed_then_nothing_changes_and_it_says_so() -> (
    None
):
    rig = scheduled()
    await rig.notice.run(NOW)
    rig.plans.states[PLAN] = "applied"

    await rig.press(rig.data(0))

    assert rig.plans.states[PLAN] == "applied"
    assert rig.chat.edits == [(7, approval_text.NOT_WAITING)]


async def test_given_a_button_pressed_twice_then_the_second_press_changes_nothing() -> None:
    rig = scheduled()
    await rig.notice.run(NOW)
    await rig.press(rig.data(0))
    rig.plans.schedule()  # a new approval of the same plan id must not be reachable with the old nonce

    await rig.press(rig.data(0))

    assert rig.plans.states[PLAN] == "scheduled"
    assert rig.chat.edits[-1] == (7, approval_text.ALREADY_DONE)


async def test_given_a_late_nonce_then_the_press_changes_nothing() -> None:
    rig = scheduled()
    await rig.notice.run(NOW)

    rig.clock[0] = NOW + timedelta(days=2)
    await rig.press(rig.data(1))

    assert rig.plans.states[PLAN] == "scheduled"
    assert not rig.lock.locked
    assert rig.chat.edits == [(7, approval_text.EXPIRED)]


async def test_given_a_button_from_another_chat_then_nothing_changes() -> None:
    rig = scheduled()
    await rig.notice.run(NOW)

    await rig.press(rig.data(0), chat_id=CHAT + 1)
    await rig.press(rig.data(1), chat_id=CHAT + 1)

    assert rig.plans.states[PLAN] == "scheduled"
    assert not rig.lock.locked
    assert rig.chat.edits == []
    assert rig.chat.notes == [approval_text.OTHER_CHAT] * 2


async def test_given_the_cancel_nonce_when_used_as_lock_then_it_is_refused() -> None:
    rig = scheduled()
    await rig.notice.run(NOW)
    _, nonce = approval_text.split_button(rig.data(0))  # type: ignore[misc]

    await rig.press(approval_text.button_data(approval_text.LOCK, nonce))

    assert not rig.lock.locked
    assert rig.plans.states[PLAN] == "scheduled"
    assert rig.chat.edits == [(7, approval_text.ALREADY_DONE)]


async def test_given_lock_then_the_web_lock_is_set_and_the_scheduled_plans_are_cancelled() -> None:
    rig = scheduled()
    rig.plans.schedule(OTHER_PLAN, count=70)
    await rig.notice.run(NOW)

    rig.clock[0] = NOW + timedelta(minutes=1)
    await rig.press(rig.data(1))

    assert rig.lock.locked
    assert set(rig.plans.states.values()) == {"cancelled"}
    assert rig.chat.edits == [(7, approval_text.locked_and_cancelled(2))]


async def test_given_lock_after_the_delay_expired_then_the_web_lock_still_holds() -> None:
    rig = scheduled()
    await rig.notice.run(NOW)
    rig.plans.states[PLAN] = "applying"

    rig.clock[0] = NOW + DELAY * 2
    await rig.press(rig.data(1))

    assert rig.lock.locked
    assert rig.plans.states[PLAN] == "cancelled"


async def test_given_the_result_notice_then_move_back_and_lock_buttons_carry_their_own_nonces() -> None:
    rig = scheduled()

    await rig.notice.send_result("Moved 60 mails.", PLAN, (Offer.MOVE_BACK, Offer.LOCK), NOW)

    message = rig.chat.sent[0]
    assert message.text == "Moved 60 mails."
    kinds = [approval_text.split_button(b.data) for b in message.buttons]
    assert [k[0] for k in kinds if k] == [approval_text.MOVE_BACK, approval_text.LOCK]
    assert kinds[0][1] != kinds[1][1]  # type: ignore[index]


async def test_given_move_back_then_one_request_is_made_and_a_second_press_changes_nothing() -> None:
    rig = Rig()
    rig.back.applied.add(PLAN)
    await rig.notice.send_result("Moved.", PLAN, (Offer.MOVE_BACK,), NOW)

    await rig.press(rig.data(0))
    await rig.press(rig.data(0))

    assert rig.back.requested == [PLAN]
    assert rig.chat.edits == [(7, approval_text.MOVE_BACK_ASKED), (7, approval_text.ALREADY_DONE)]


async def test_given_move_back_for_a_plan_that_is_not_applied_then_nothing_is_requested_and_it_says_so() -> None:
    rig = Rig()
    await rig.notice.send_result("Moved.", PLAN, (Offer.MOVE_BACK,), NOW)

    await rig.press(rig.data(0))

    assert rig.back.requested == []
    assert rig.chat.edits == [(7, approval_text.MOVE_BACK_UNAVAILABLE)]


def test_given_malformed_plan_buttons_then_they_are_not_plan_buttons() -> None:
    assert approval_text.split_button("plancancel:short") is None
    assert approval_text.split_button("catundo:" + "A" * 22) is None
    assert approval_text.split_button("plancancel:" + "A" * 22 + ":x") is None
    assert approval_text.split_button("plancancel:" + "A" * 22) == ("plancancel", "A" * 22)
