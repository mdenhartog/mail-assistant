"""U-mail-categories-07 criterion 3 (AC-48): a second, late or foreign press changes nothing and says so."""

from __future__ import annotations

from datetime import timedelta

from app.adapters.telegram_inbox import Command
from app.usecases.telegram_actions import ACTION_TTL
from tests.list_notice_support import AT, CHAT, FakeListStore, Rig, cats, seeded


async def _announced() -> tuple[Rig, str]:
    rig = seeded()
    rig.store.save(cats("Bills"))
    await rig.notice.run(AT)
    return rig, rig.chat.sent[0].buttons[0].data


def _unchanged(store: FakeListStore, versions: int) -> bool:
    return store.latest == versions


async def test_given_undo_pressed_twice_then_the_second_press_changes_nothing_and_says_so() -> None:
    rig, undo = await _announced()
    await rig.press(undo)
    versions = rig.store.latest

    await rig.press(undo, message_id=8)

    assert _unchanged(rig.store, versions)
    assert rig.chat.edits[-1] == (8, "Already done. Nothing was changed.")


async def test_given_a_late_press_then_nothing_changes_and_the_answer_says_expired() -> None:
    rig, undo = await _announced()
    rig.clock[0] = AT + ACTION_TTL + timedelta(seconds=1)

    await rig.press(undo)

    assert _unchanged(rig.store, 2)
    assert rig.chat.edits[-1][1] == "Expired. Nothing was changed."


async def test_given_another_chat_then_nothing_changes_the_owner_is_told_and_the_button_still_works() -> None:
    rig, undo = await _announced()

    await rig.press(undo, chat_id=CHAT + 1)

    assert _unchanged(rig.store, 2)
    assert rig.chat.notes == ["A button from another chat was ignored. Nothing was changed."]
    assert not rig.chat.edits
    await rig.press(undo)
    assert rig.store.latest == 3


async def test_given_a_list_changed_after_the_notice_then_undo_refuses_and_says_so() -> None:
    rig, undo = await _announced()
    rig.store.save(cats("Newer"))

    await rig.press(undo)

    assert rig.store.latest == 3
    assert "changed since" in rig.chat.edits[-1][1]


async def test_given_a_made_up_button_then_it_is_answered_as_done_and_nothing_changes() -> None:
    rig, _ = await _announced()

    await rig.buttons.on_button(Command("button", "catundo:x", CHAT, 9, "cb", 2), "catundo", "z" * 22)

    assert _unchanged(rig.store, 2)
    assert rig.chat.edits[-1][1] == "Already done. Nothing was changed."
