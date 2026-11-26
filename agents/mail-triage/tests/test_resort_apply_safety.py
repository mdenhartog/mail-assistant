"""U-mail-categories-15, criteria 4, 5, 6: concurrent runs, a crash between two writes, and Lock during an apply."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest

from app.core.resort_plan import ItemState, PlanState
from app.usecases.resort_apply import SkipReason
from tests.resort_apply_support import FINANCE, OTHER_ID, TRAVEL, ApplyRig, item


async def test_two_apply_runs_at_once_move_each_mail_once() -> None:
    rig = ApplyRig(batch_size=2)
    mails = [rig.mail(("INBOX", rig.finance)) for _ in range(5)]
    plan = rig.store.add_plan([item(m, FINANCE, TRAVEL) for m in mails])

    await asyncio.gather(rig.apply().run_once(), rig.apply().run_once())

    assert rig.modifies() == 2 * len(mails)  # one add and one remove per mail, no more
    assert all(rig.labels_of(m) == {"INBOX", "Travel"} for m in mails)
    assert rig.store.state(plan) is PlanState.APPLIED
    assert len(rig.telegram.texts) == 1  # one result notice


async def test_a_database_failure_after_the_gmail_change_ends_applied_without_a_second_move() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])
    rig.store.fail_finish_item_once = True

    with pytest.raises(ConnectionError):
        await rig.apply().run_once()
    assert rig.modifies() == 2
    assert rig.store.item(plan, mid).state is ItemState.APPROVED

    rig.clock.advance(timedelta(minutes=6))  # the lease of the crashed run ends
    await rig.apply().run_once()

    assert rig.modifies() == 2  # nothing moved twice
    assert rig.store.state(plan) is PlanState.APPLIED
    assert rig.labels_of(mid) == {"INBOX", "Travel"}
    assert len(await rig.store.audit_moves(plan)) == 1


async def test_a_crash_between_adding_and_removing_is_finished_on_retry_without_losing_the_mail_label() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])

    def crash(_mid: str) -> None:
        raise ConnectionResetError("the process dies between the two calls")

    rig.mailbox.on_remove = crash
    with pytest.raises(ConnectionResetError):
        await rig.apply().run_once()
    assert rig.labels_of(mid) == {"INBOX", "Finance", "Travel"}  # never without a label

    rig.mailbox.on_remove = None
    rig.clock.advance(timedelta(minutes=6))
    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Travel"}
    assert rig.modifies() == 2  # the add ran once, the retry only removed
    assert rig.store.state(plan) is PlanState.APPLIED


async def test_apply_retry_with_intent_skips_mail_that_gained_archive() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])

    def crash(_mid: str) -> None:
        raise ConnectionResetError("the process dies between the two calls")

    rig.mailbox.on_remove = crash
    with pytest.raises(ConnectionResetError):
        await rig.apply().run_once()
    rig.mailbox.on_remove = None
    rig.gmail.mail_table[mid].labels.add(rig.gmail.add_label("Archive"))  # the user archived it meanwhile
    rig.clock.advance(timedelta(minutes=6))

    await rig.apply().run_once()

    assert rig.store.item(plan, mid).state is ItemState.SKIPPED
    assert "Finance" in rig.labels_of(mid)  # the old label is not removed from a mail that left the scope


async def test_a_lost_answer_after_the_add_is_finished_on_retry() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])
    rig.gmail.fail_after_next_change()

    with pytest.raises(ConnectionResetError):
        await rig.apply().run_once()
    rig.clock.advance(timedelta(minutes=6))
    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Travel"}
    assert rig.store.state(plan) is PlanState.APPLIED


async def test_a_mail_that_carries_the_new_label_without_our_record_is_not_ours_and_is_skipped() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.travel))  # the user filed it there before we got to it
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    assert rig.store.item(plan, mid).state is ItemState.SKIPPED
    assert await rig.store.audit_moves(plan) == []


async def test_lock_during_an_apply_stops_before_the_next_batch() -> None:
    rig = ApplyRig(batch_size=2)
    mails = [rig.mail(("INBOX", rig.finance)) for _ in range(5)]
    plan = rig.store.add_plan([item(m, FINANCE, TRAVEL) for m in mails])
    rig.lock.locked_after = 1  # the first check passes, the second finds the lock

    await rig.apply().run_once()

    moved = [m for m in mails if rig.labels_of(m) == {"INBOX", "Travel"}]
    assert moved == mails[:2]  # the first batch stays moved
    assert rig.store.state(plan) is PlanState.CANCELLED
    assert rig.telegram.texts == []


async def test_a_scheduled_plan_is_cancelled_instead_of_started_while_locked() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])
    rig.lock.locked = True

    await rig.apply().run_once()

    assert rig.store.state(plan) is PlanState.CANCELLED
    assert rig.modifies() == 0


async def test_a_plan_cancelled_during_the_apply_stops_before_the_next_batch() -> None:
    rig = ApplyRig(batch_size=1)
    mails = [rig.mail(("INBOX", rig.finance)) for _ in range(3)]
    plan = rig.store.add_plan([item(m, FINANCE, TRAVEL) for m in mails])

    def cancel_after_first(_mid: str) -> None:
        row = rig.store.plans[plan]
        row.due = replace(row.due, state=PlanState.CANCELLED)

    rig.mailbox.on_add = cancel_after_first
    await rig.apply().run_once()

    assert sum(rig.labels_of(m) == {"INBOX", "Travel"} for m in mails) == 1


async def test_the_archive_label_wins_and_the_mail_is_left_alone_even_when_the_archive_was_renamed_by_hand() -> None:
    rig = ApplyRig()
    archive = rig.gmail.add_label(
        "Done"
    )  # the archive setting is Archive; the user renamed the label, the id is stored
    rig.store.stored_ids["archive"] = archive
    mid = rig.mail(("INBOX", rig.finance, archive))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    assert rig.store.item(plan, mid).reason is SkipReason.OUT_OF_SCOPE
    assert rig.mailbox.writes == []
    assert rig.labels_of(mid) == {"INBOX", "Finance", "Done"}


async def test_a_move_adds_and_removes_managed_labels_by_their_stored_id_even_after_a_hand_rename() -> None:
    rig = ApplyRig()
    rig.gmail.label_table[rig.travel] = "Trips"  # renamed by hand; its id is the one the database stored
    rig.store.stored_ids[TRAVEL] = rig.travel
    mid = rig.mail(("INBOX", rig.finance))
    rig.store.add_plan([item(mid, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    assert rig.mailbox.writes == [("add", mid, rig.travel), ("remove", mid, rig.finance)]
    assert rig.labels_of(mid) == {"INBOX", "Trips"}


async def test_a_label_without_a_stored_id_is_created_by_the_name_of_the_other_setting() -> None:
    rig = ApplyRig()
    rig.store.other_name = "Misc"
    mid = rig.mail(("INBOX", rig.finance))
    rig.store.add_plan([item(mid, FINANCE, OTHER_ID)])

    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Misc"}
