"""U-mail-categories-22, open point (g): the result notice of an apply goes through U-16's ``ApprovalNotice``.

``ApplyNotifier.result`` hands the text, the plan and the offers to ``ApprovalNotice.send_result`` (Move back and Lock
buttons, each with its own nonce in ``telegram_action``); a plain note is a plain note. The text is escaped here because
the notice is shown as HTML and names a label.
"""

from __future__ import annotations

import uuid

from app.core import approval_text
from app.usecases.approval_notice import ApprovalNotice
from app.usecases.resort_apply import Offer
from app.usecases.resort_notice import TelegramApplyNotifier
from app.usecases.telegram_actions import Redeemed, Refusal, TelegramActions
from tests.approval_notice_support import NOW, FakePlanStore
from tests.list_notice_support import CHAT, FakeActionStore, Nonces, RecordingChat

PLAN = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _rig() -> tuple[TelegramApplyNotifier, TelegramActions, FakeActionStore, RecordingChat]:
    store, chat = FakeActionStore(), RecordingChat()
    actions = TelegramActions(store, Nonces())
    notice = ApprovalNotice(actions, FakePlanStore(), chat, chat_id=CHAT)
    return TelegramApplyNotifier(chat, notice, now=lambda: NOW), actions, store, chat


async def test_the_result_notice_has_a_move_back_and_a_lock_button_with_one_nonce_each() -> None:
    notifier, _actions, store, chat = _rig()

    await notifier.result("Plan applied: 3 moved.", plan_id=PLAN, offers=(Offer.MOVE_BACK, Offer.LOCK))

    [message] = chat.sent
    assert message.text == "Plan applied: 3 moved."
    assert [b.label for b in message.buttons] == [approval_text.MOVE_BACK_LABEL, approval_text.LOCK_LABEL]
    assert len({b.data for b in message.buttons}) == 2
    assert {r.target for r in store.rows.values()} == {str(PLAN)}
    assert {r.kind for r in store.rows.values()} == {"plan_move_back", "plan_lock"}


async def test_each_button_is_redeemable_once_for_its_own_kind() -> None:
    notifier, actions, _store, chat = _rig()
    await notifier.result("done", plan_id=PLAN, offers=(Offer.MOVE_BACK, Offer.LOCK))
    back, lock = (approval_text.split_button(b.data) for b in chat.sent[0].buttons)
    assert back is not None
    assert lock is not None

    assert await actions.redeem(back[1], "plan_move_back", CHAT, NOW) == Redeemed(str(PLAN))
    assert await actions.redeem(back[1], "plan_move_back", CHAT, NOW) is Refusal.DONE
    assert await actions.redeem(lock[1], "plan_move_back", CHAT, NOW) is Refusal.DONE
    assert await actions.redeem(lock[1], "plan_lock", CHAT, NOW) == Redeemed(str(PLAN))


async def test_the_text_is_escaped_for_telegram_html() -> None:
    notifier, _actions, _store, chat = _rig()

    await notifier.result("Labels now empty: <b>x</b> & y", plan_id=PLAN, offers=())

    assert chat.sent[0].text == "Labels now empty: &lt;b&gt;x&lt;/b&gt; &amp; y"


async def test_a_plain_note_is_sent_as_a_note() -> None:
    notifier, _actions, _store, chat = _rig()

    await notifier.say("Move back done.")

    assert chat.notes == ["Move back done."]
    assert chat.sent == []
