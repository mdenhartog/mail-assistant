"""U-mail-categories-22, open point (g): the result notice of an apply carries a Move back and a Lock button.

Each button has its own single-use nonce in ``telegram_action`` (ADR-0046 point 7): only the hash is stored, with the
chat, the kind and the plan as target. Pressing a button is built elsewhere (U-mail-categories-16); here the notice, the
stored nonces and what the router can later redeem.
"""

from __future__ import annotations

import uuid

from app.usecases.resort_apply import Offer
from app.usecases.resort_notice import LOCK_ACTION, MOVE_BACK_ACTION, TelegramApplyNotifier, split_button
from app.usecases.telegram_actions import Redeemed, Refusal, TelegramActions, digest
from tests.list_notice_support import AT, CHAT, FakeActionStore, Nonces, RecordingChat

PLAN = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _rig() -> tuple[TelegramApplyNotifier, TelegramActions, FakeActionStore, RecordingChat]:
    store, chat = FakeActionStore(), RecordingChat()
    actions = TelegramActions(store, Nonces())
    return TelegramApplyNotifier(chat, actions, chat_id=CHAT, now=lambda: AT), actions, store, chat


async def test_the_result_notice_has_a_move_back_and_a_lock_button_with_one_nonce_each() -> None:
    notifier, _actions, store, chat = _rig()

    await notifier.result("Plan applied: 3 moved.", plan_id=PLAN, offers=(Offer.MOVE_BACK, Offer.LOCK))

    [message] = chat.sent
    assert message.text == "Plan applied: 3 moved."
    assert [b.label for b in message.buttons] == ["Move back", "Lock web sign-in"]
    parsed = [split_button(b.data) for b in message.buttons]
    assert [p[0] for p in parsed if p] == [MOVE_BACK_ACTION, LOCK_ACTION]
    assert len({p[1] for p in parsed if p}) == 2
    assert {r.kind for r in store.rows.values()} == {"move_back", "lock"}
    assert {r.target for r in store.rows.values()} == {str(PLAN)}
    assert {r.chat_id for r in store.rows.values()} == {CHAT}


async def test_only_the_hash_of_a_nonce_is_stored_and_each_button_is_redeemable_once_for_its_kind() -> None:
    notifier, actions, store, chat = _rig()
    await notifier.result("done", plan_id=PLAN, offers=(Offer.MOVE_BACK, Offer.LOCK))
    back, lock = (split_button(b.data) for b in chat.sent[0].buttons)
    assert back is not None
    assert lock is not None
    assert all(nonce not in store.rows and digest(nonce) in store.rows for _action, nonce in (back, lock))

    assert await actions.redeem(back[1], "move_back", CHAT, AT) == Redeemed(str(PLAN))
    assert await actions.redeem(back[1], "move_back", CHAT, AT) is Refusal.DONE  # once
    assert await actions.redeem(lock[1], "move_back", CHAT, AT) is Refusal.DONE  # a lock nonce is no move back
    assert await actions.redeem(lock[1], "lock", CHAT, AT) == Redeemed(str(PLAN))


async def test_an_offer_that_is_not_asked_for_gets_no_button_and_no_nonce() -> None:
    notifier, _actions, store, chat = _rig()

    await notifier.result("done", plan_id=PLAN, offers=(Offer.LOCK,))

    assert [b.label for b in chat.sent[0].buttons] == ["Lock web sign-in"]
    assert {r.kind for r in store.rows.values()} == {"lock"}


async def test_the_text_is_escaped_for_telegram_html() -> None:
    notifier, _actions, _store, chat = _rig()

    await notifier.result("Labels now empty: <b>x</b> & y", plan_id=PLAN, offers=())

    assert chat.sent[0].text == "Labels now empty: &lt;b&gt;x&lt;/b&gt; &amp; y"


async def test_a_plain_note_is_sent_as_a_note() -> None:
    notifier, _actions, _store, chat = _rig()

    await notifier.say("Move back done.")

    assert chat.notes == ["Move back done."]
    assert chat.sent == []


def test_button_data_that_is_not_ours_is_not_split() -> None:
    assert split_button("catundo:" + "a" * 22) is None
    assert split_button("planback:short") is None
    assert split_button(f"planback:{'a' * 22}") == (MOVE_BACK_ACTION, "a" * 22)
