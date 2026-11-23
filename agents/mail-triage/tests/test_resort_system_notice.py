"""U-label-structure-23, criteria 2 and 3: the notice of a system-approved plan and its buttons (ADR-0056 point 5).

The notice names the numbers (what moves on its own, what waits for review) and offers Cancel, Move back and Lock, with
a line that says what Lock does. Cancel, Move back (Undo) and Lock before the apply cancel the plan: nothing moves.
"""

from __future__ import annotations

from datetime import timedelta

from app.core import approval_text
from app.core.resort_plan import PlanKind
from tests.approval_notice_support import NOW, PLAN, Rig


def _system_rig(count: int = 12, review: int = 5) -> Rig:
    rig = Rig()
    rig.plans.schedule(count=count, kind=PlanKind.AUTO, review=review)
    return rig


async def test_given_a_system_approved_plan_when_noticed_then_the_numbers_and_three_buttons_are_sent() -> None:
    rig = _system_rig(12, 5)

    await rig.notice.run(NOW)
    await rig.notice.run(NOW)

    (message,) = rig.chat.sent
    assert "12 mails move on their own in 15 minutes (at 09:15 UTC)" in message.text
    assert "5 wait for your review in the web app" in message.text
    assert "Only labels change." in message.text
    assert approval_text.LOCK_EXPLAINED in message.text  # the line that says what Lock does
    assert [b.label for b in message.buttons] == [
        approval_text.CANCEL_LABEL,
        approval_text.MOVE_BACK_LABEL,
        approval_text.LOCK_LABEL,
    ]
    assert [approval_text.split_button(b.data)[0] for b in message.buttons] == [  # type: ignore[index]
        approval_text.CANCEL,
        approval_text.MOVE_BACK,
        approval_text.LOCK,
    ]


async def test_given_nothing_waits_for_review_when_noticed_then_the_review_sentence_is_left_out() -> None:
    rig = _system_rig(1, 0)

    await rig.notice.run(NOW)

    (message,) = rig.chat.sent
    assert "1 mail moves on its own" in message.text
    assert "review" not in message.text


async def test_given_a_plan_approved_by_the_user_when_noticed_then_the_notice_is_the_old_one() -> None:
    rig = Rig()
    rig.plans.schedule()

    await rig.notice.run(NOW)

    (message,) = rig.chat.sent
    assert [b.label for b in message.buttons] == [approval_text.CANCEL_LABEL, approval_text.LOCK_LABEL]


async def test_given_cancel_before_the_apply_when_pressed_then_the_plan_is_cancelled() -> None:
    rig = _system_rig()
    await rig.notice.run(NOW)

    rig.clock[0] = NOW + timedelta(minutes=5)
    await rig.press(rig.data(0))

    assert rig.plans.states[PLAN] == "cancelled"
    assert rig.chat.edits == [(7, approval_text.CANCELLED)]


async def test_given_move_back_before_the_apply_when_pressed_then_the_plan_is_cancelled_not_asked_for_a_restore() -> (
    None
):
    rig = _system_rig()
    await rig.notice.run(NOW)

    rig.clock[0] = NOW + timedelta(minutes=5)
    await rig.press(rig.data(1))

    assert rig.plans.states[PLAN] == "cancelled"  # Undo before the apply: nothing moved, so nothing to restore
    assert rig.back.requested == []
    assert rig.chat.edits == [(7, approval_text.CANCELLED)]


async def test_given_lock_before_the_apply_when_pressed_then_the_web_is_locked_and_the_plan_is_cancelled() -> None:
    rig = _system_rig()
    await rig.notice.run(NOW)

    await rig.press(rig.data(2))

    assert rig.lock.locked
    assert rig.plans.states[PLAN] == "cancelled"
    assert rig.chat.edits == [(7, approval_text.locked_and_cancelled(1))]


async def test_given_move_back_after_the_apply_when_pressed_then_a_restore_is_requested() -> None:
    rig = _system_rig()
    await rig.notice.run(NOW)
    rig.plans.states[PLAN] = "applied"
    rig.back.applied.add(PLAN)

    await rig.press(rig.data(1))

    assert rig.back.requested == [PLAN]
    assert rig.chat.edits == [(7, approval_text.MOVE_BACK_ASKED)]


async def test_given_move_back_after_the_delay_when_the_apply_has_started_then_it_is_refused_as_too_late() -> None:
    rig = _system_rig()
    await rig.notice.run(NOW)

    rig.clock[0] = NOW + timedelta(minutes=15)  # due: the apply may have started
    await rig.press(rig.data(1))

    assert rig.plans.states[PLAN] == "scheduled"
    assert rig.back.requested == []
    assert rig.chat.edits == [(7, approval_text.TOO_LATE)]
