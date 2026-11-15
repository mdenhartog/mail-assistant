"""U-mail-categories-22, open point (e): a mail that keeps failing ends ``failed`` and never blocks its plan.

The mailbox port raises ``MailFailed`` for a Gmail failure that is neither a gone mail nor a retryable one the adapter
already retried. The apply counts the attempts per item in the store and fails the item after ``MAX_ITEM_ATTEMPTS``.
"""

from __future__ import annotations

from app.core.resort_plan import ItemState, PlanState
from app.usecases.resort_apply import MAX_ITEM_ATTEMPTS
from tests.resort_apply_support import FINANCE, TRAVEL, ApplyRig, item


async def test_a_mail_that_always_fails_ends_failed_and_the_other_mails_are_moved_and_the_plan_ends_applied() -> None:
    rig = ApplyRig()
    first, bad, last = (rig.mail(("INBOX", rig.finance)) for _ in range(3))
    plan = rig.store.add_plan([item(m, FINANCE, TRAVEL) for m in (first, bad, last)])
    rig.mailbox.failing_adds[bad] = -1

    await rig.apply().run_once()

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

    await rig.apply().run_once()

    assert rig.store.item(plan, mid).state is ItemState.APPLIED
    assert rig.store.attempts[(plan, mid)] == 1
    assert rig.labels_of(mid) == {"INBOX", "Assistant/Travel"}


async def test_a_failing_read_counts_like_a_failing_write() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])
    rig.mailbox.failing_fetches.add(mid)

    await rig.apply().run_once()

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
