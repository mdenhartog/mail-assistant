"""U-mail-categories-07 criterion 3 (AC-48, ADR-0046 item 7): a button nonce is hashed, bound and used once."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from app.usecases.telegram_actions import ACTION_TTL, Redeemed, Refusal, TelegramActions
from tests.list_notice_support import AT, CHAT, FakeActionStore, Nonces


def _actions(store: FakeActionStore) -> TelegramActions:
    return TelegramActions(store, Nonces())


async def test_given_an_issued_nonce_then_only_its_hash_is_stored_with_chat_kind_target_and_expiry() -> None:
    store = FakeActionStore()

    nonce = await _actions(store).issue("undo", "3-4", CHAT, AT)

    (row,) = store.rows.values()
    assert nonce not in row.nonce_hash
    assert row.nonce_hash == hashlib.sha256(nonce.encode()).hexdigest()
    assert (row.chat_id, row.kind, row.target, row.expires_at, row.used_at) == (
        CHAT,
        "undo",
        "3-4",
        AT + ACTION_TTL,
        None,
    )


async def test_given_a_nonce_when_redeemed_twice_then_the_second_press_is_refused_as_done() -> None:
    store = FakeActionStore()
    actions = _actions(store)
    nonce = await actions.issue("undo", "3-4", CHAT, AT)

    first = await actions.redeem(nonce, "undo", CHAT, AT)
    second = await actions.redeem(nonce, "undo", CHAT, AT)

    assert first == Redeemed("3-4")
    assert second is Refusal.DONE


async def test_given_a_late_press_then_it_is_refused_as_expired() -> None:
    store = FakeActionStore()
    actions = _actions(store)
    nonce = await actions.issue("undo", "3-4", CHAT, AT)

    outcome = await actions.redeem(nonce, "undo", CHAT, AT + ACTION_TTL + timedelta(seconds=1))

    assert outcome is Refusal.EXPIRED


async def test_given_another_chat_then_it_is_refused_and_the_nonce_is_not_used_up() -> None:
    store = FakeActionStore()
    actions = _actions(store)
    nonce = await actions.issue("undo", "3-4", CHAT, AT)

    outcome = await actions.redeem(nonce, "undo", CHAT + 1, AT)

    assert outcome is Refusal.OTHER_CHAT
    assert await actions.redeem(nonce, "undo", CHAT, AT) == Redeemed("3-4")


async def test_given_an_unknown_nonce_or_the_wrong_kind_then_it_is_refused_as_done() -> None:
    store = FakeActionStore()
    actions = _actions(store)
    nonce = await actions.issue("lock", "3-4", CHAT, AT)

    assert await actions.redeem("x" * 22, "undo", CHAT, AT) is Refusal.DONE
    assert await actions.redeem(nonce, "undo", CHAT, AT) is Refusal.DONE
