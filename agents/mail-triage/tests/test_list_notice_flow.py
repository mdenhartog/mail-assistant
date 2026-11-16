"""U-mail-categories-07 criteria 1, 2, 5, 6, 7 (AC-29 to AC-31, AC-36, MC-14): the notice, one per burst, and Undo."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from tests.fakes.seeds import CANARIES
from tests.list_notice_support import AT, LATER, Rig, cats, seeded

NIGHT = datetime(2026, 11, 14, 2, 30, tzinfo=UTC)  # quiet hours at the user's side; nothing here reads a policy


async def test_given_a_web_change_in_quiet_hours_when_the_agent_runs_then_one_notice_with_old_new_and_undo() -> None:
    rig = seeded()
    rig.store.save(cats("Bills", "Work"))

    await rig.notice.run(NIGHT)

    (message,) = rig.chat.sent
    for fact in ("Added: Work", "Removed: Travel"):
        assert fact in message.text
    assert [b.label for b in message.buttons] == ["Undo", "Undo and lock web sign-in"]
    assert rig.store.cursor == 2


async def test_given_the_notice_was_sent_when_the_agent_runs_again_then_there_is_no_second_one() -> None:
    rig = seeded()
    rig.store.save(cats("Bills"))

    await rig.notice.run(AT)
    await rig.notice.run(AT)

    assert len(rig.chat.sent) == 1


async def test_given_a_failed_send_then_the_cursor_stays_and_the_next_run_announces_it() -> None:
    rig = seeded()
    rig.store.save(cats("Bills"))
    rig.chat.fail_send = True

    with pytest.raises(RuntimeError):
        await rig.notice.run(AT)
    assert rig.store.cursor == 1
    rig.chat.fail_send = False
    await rig.notice.run(AT)

    assert len(rig.chat.sent) == 1


async def test_given_the_agents_own_versions_then_they_are_skipped_without_a_notice() -> None:
    rig = Rig()
    rig.store.save(cats("Bills"), channel="telegram")  # the seed

    await rig.notice.run(AT)

    assert not rig.chat.sent
    assert rig.store.cursor == 1


async def test_given_a_burst_of_three_changes_then_one_notice_and_undo_restores_the_list_from_before() -> None:
    rig = seeded()
    for names in (("Bills",), ("Bills", "Hacked"), ("Everything",)):
        rig.store.save(cats(*names))

    await rig.notice.run(AT)
    (message,) = rig.chat.sent
    assert "3 changes" in message.text
    await rig.press(message.buttons[0].data)

    assert rig.store.audit[-1].new == cats("Bills", "Travel")
    assert rig.store.latest == 5  # a new version, not a rewrite of an old one
    assert rig.chat.edits[0][1].startswith("Undone")


async def test_given_the_agents_own_undo_then_exactly_one_notice_is_produced() -> None:
    rig = seeded()
    rig.store.save(cats("Bills"))
    await rig.notice.run(AT)
    await rig.press(rig.chat.sent[0].buttons[0].data)

    await rig.notice.run(LATER)  # the Undo is version 3, written by the agent

    assert len(rig.chat.sent) == 1  # the one notice of the web change; the Undo is answered by editing it
    assert len(rig.chat.edits) == 1
    assert rig.store.cursor == 3


async def test_given_the_lock_button_then_the_lock_is_set_and_the_list_is_restored() -> None:
    rig = seeded()
    rig.store.save(cats("Bills"))
    await rig.notice.run(AT)

    await rig.press(rig.chat.sent[0].buttons[1].data)

    assert rig.lock.locked
    assert rig.store.audit[-1].new == cats("Bills", "Travel")
    assert "locked" in rig.chat.edits[0][1]


async def test_given_the_lock_button_after_the_list_changed_again_then_the_lock_still_holds() -> None:
    rig = seeded()
    rig.store.save(cats("Bills"))
    await rig.notice.run(AT)
    rig.store.save(cats("Other things"))  # a newer change, not yet announced

    await rig.press(rig.chat.sent[0].buttons[1].data)

    assert rig.lock.locked
    assert rig.store.audit[-1].new == cats("Other things")
    assert "changed since" in rig.chat.edits[0][1]


async def test_given_a_change_and_an_undo_then_each_has_an_append_only_audit_row_with_channel_and_actor() -> None:
    rig = seeded()
    rig.store.save(cats("Bills"))
    await rig.notice.run(AT)
    before = list(rig.store.audit)

    await rig.press(rig.chat.sent[0].buttons[0].data)

    assert rig.store.audit[: len(before)] == before  # nothing earlier was touched
    web, undo = rig.store.audit[1], rig.store.audit[2]
    assert (web.channel, undo.channel) == ("web", "telegram")
    for row in (web, undo):
        assert re.fullmatch(r"[0-9a-f]{64}", row.actor_digest)
    assert web.actor_digest != undo.actor_digest


async def test_given_any_notice_or_answer_then_it_holds_no_sender_or_subject() -> None:
    rig = seeded()
    rig.store.save(cats("Bills"))
    await rig.notice.run(AT)
    await rig.press(rig.chat.sent[0].buttons[0].data)
    await rig.press(rig.chat.sent[0].buttons[0].data)  # a second press is answered too

    texts = [m.text for m in rig.chat.sent] + [t for _, t in rig.chat.edits] + rig.chat.notes
    assert texts
    for text in texts:
        assert not [c for c in CANARIES if c in text.casefold()]  # the double also raises when one gets through
    assert rig.chat.texts == texts
