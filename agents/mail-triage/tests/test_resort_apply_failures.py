"""U-mail-categories-22, open point (e): a mail that keeps failing ends ``failed`` and never blocks its plan.

The mailbox port raises ``MailFailed`` for a Gmail failure that is neither a gone mail nor a retryable one the adapter
already retried. The apply counts the attempts per item in the store and fails the item after ``MAX_ITEM_ATTEMPTS``.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.resort_plan import ItemState, PlanState
from app.usecases.resort_apply import MAX_ITEM_ATTEMPTS
from tests.resort_apply_support import FINANCE, LEASE, TRAVEL, ApplyRig, item


async def _run(rig: ApplyRig, runs: int = 1) -> None:
    """Poll the apply ``runs`` times; a plan left ``applying`` is taken again once its lease has ended."""
    for _ in range(runs):
        await rig.apply().run_once()
        rig.clock.advance(LEASE + timedelta(seconds=1))


async def test_a_mail_that_always_fails_ends_failed_and_the_other_mails_are_moved_and_the_plan_ends_applied() -> None:
    rig = ApplyRig()
    first, bad, last = (rig.mail(("INBOX", rig.finance)) for _ in range(3))
    plan = rig.store.add_plan([item(m, FINANCE, TRAVEL) for m in (first, bad, last)])
    rig.mailbox.failing_adds[bad] = -1

    await _run(rig, MAX_ITEM_ATTEMPTS)

    assert rig.store.state(plan) is PlanState.APPLIED
    assert rig.store.item(plan, bad).state is ItemState.FAILED
    assert rig.store.attempts[(plan, bad)] == MAX_ITEM_ATTEMPTS
    assert rig.labels_of(bad) == {"INBOX", "Assistant/Finance"}  # untouched
    assert rig.labels_of(first) == rig.labels_of(last) == {"INBOX", "Assistant/Travel"}
    assert "1 failed" in rig.telegram.texts[-1]
    assert len(rig.telegram.texts) == 1


async def test_a_mail_that_fails_once_is_tried_again_and_ends_applied() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])
    rig.mailbox.failing_adds[mid] = 1

    await _run(rig, 2)

    assert rig.store.state(plan) is PlanState.APPLIED
    assert "1 moved, 0 skipped" in rig.telegram.texts[-1]  # applied items leave the plan
    assert rig.store.attempts[(plan, mid)] == 1
    assert rig.labels_of(mid) == {"INBOX", "Assistant/Travel"}


async def test_a_mail_that_fails_twice_is_tried_once_per_run_and_ends_applied_in_the_third() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])
    rig.mailbox.failing_adds[mid] = 2  # a short Gmail outage: the add fails twice, then works

    await rig.apply().run_once()  # run 1: one attempt, not three in a row
    assert rig.store.attempts[(plan, mid)] == 1
    assert rig.store.item(plan, mid).state is ItemState.APPROVED
    assert rig.store.state(plan) is PlanState.APPLYING  # not finished while an item waits for its next run

    await rig.apply().run_once()  # the next poll, lease still held: nothing is tried
    assert rig.store.attempts[(plan, mid)] == 1

    rig.clock.advance(LEASE + timedelta(seconds=1))
    await rig.apply().run_once()  # run 2
    assert rig.store.attempts[(plan, mid)] == 2
    rig.clock.advance(LEASE + timedelta(seconds=1))
    await rig.apply().run_once()  # run 3 succeeds

    assert rig.store.state(plan) is PlanState.APPLIED
    assert rig.labels_of(mid) == {"INBOX", "Assistant/Travel"}
    assert "1 moved" in rig.telegram.texts[-1]


async def test_a_failed_mail_does_not_hide_the_mails_behind_it_in_a_full_batch() -> None:
    rig = ApplyRig(batch_size=2)
    bad = [rig.mail(("INBOX", rig.finance)) for _ in range(2)]
    good = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(m, FINANCE, TRAVEL) for m in (*bad, good)])
    for mid in bad:
        rig.mailbox.failing_adds[mid] = -1

    await _run(rig, MAX_ITEM_ATTEMPTS)

    assert rig.labels_of(good) == {"INBOX", "Assistant/Travel"}
    assert rig.store.state(plan) is PlanState.APPLIED


async def test_a_failing_read_counts_like_a_failing_write() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])
    rig.mailbox.failing_fetches.add(mid)

    await _run(rig, MAX_ITEM_ATTEMPTS)

    assert rig.store.item(plan, mid).state is ItemState.FAILED
    assert rig.store.state(plan) is PlanState.APPLIED


async def test_move_back_skips_a_mail_whose_restore_keeps_failing_and_still_finishes() -> None:
    rig = ApplyRig()
    good, bad = (rig.mail(("INBOX", rig.finance)) for _ in range(2))
    plan = rig.store.add_plan([item(good, FINANCE, TRAVEL), item(bad, FINANCE, TRAVEL)])
    await rig.apply().run_once()
    rig.mailbox.failing_adds[bad] = -1
    rig.store.request_move_back(plan)

    await rig.move_back().run_once()

    assert rig.labels_of(good) == {"INBOX", "Assistant/Finance"}
    assert rig.labels_of(bad) == {"INBOX", "Assistant/Travel"}  # left as it is
    assert plan in rig.store.processed
    assert "1 restored, 1 skipped" in rig.telegram.texts[-1]
