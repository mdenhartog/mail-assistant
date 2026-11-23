"""U-mail-categories-15, criteria 1, 2, 3, 7, 9: what an apply moves, what it skips and what it reports."""

from __future__ import annotations

from datetime import timedelta

from app.core.resort_plan import ItemState, PlanState
from app.usecases.resort_apply import Offer, SkipReason
from tests.resort_apply_support import FINANCE, GOOGLE_AUTH, NEWSLETTER, OTHER_ID, TRAVEL, ApplyRig, item


async def test_an_approved_item_swaps_the_assistant_label_and_nothing_else_changes() -> None:
    rig = ApplyRig()
    moved = rig.mail(("INBOX", rig.finance))
    unfiled = rig.mail(("INBOX",))  # no label yet: Other
    plan = rig.store.add_plan([item(moved, FINANCE, TRAVEL), item(unfiled, OTHER_ID, FINANCE)])

    await rig.apply().run_once()

    assert rig.labels_of(moved) == {"INBOX", "Assistant/Travel"}
    assert rig.labels_of(unfiled) == {"INBOX", "Assistant/Finance"}  # INBOX stays; only Assistant/ labels change
    assert set(rig.gmail.mail_table) == {moved, unfiled}  # nothing deleted
    assert set(rig.gmail.calls) <= {"labels.list", "labels.get", "labels.create", "messages.get", "messages.modify"}
    assert rig.store.state(plan) is PlanState.APPLIED
    audit = {m.message_id: (m.old_label, m.new_label) for m in await rig.store.audit_moves(plan)}
    assert audit == {moved: (rig.finance, rig.travel), unfiled: ("", rig.finance)}
    assert await rig.store.item_counts(plan) == {}  # applied items are removed at once


async def test_a_plan_that_is_not_due_yet_is_left_alone() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)], apply_after=timedelta(minutes=15))

    await rig.apply().run_once()
    assert rig.store.state(plan) is PlanState.SCHEDULED
    assert rig.modifies() == 0

    rig.clock.advance(timedelta(minutes=15))
    await rig.apply().run_once()
    assert rig.store.state(plan) is PlanState.APPLIED


async def test_mail_changed_meanwhile_is_skipped_with_a_reason() -> None:
    rig = ApplyRig()
    archive = rig.gmail.add_label("Archive")
    other_label = rig.mail(("INBOX", rig.travel))  # the user moved it to Travel
    deleted = rig.mail(("INBOX", rig.finance))
    archived = rig.mail(("INBOX", rig.finance, archive))
    left_inbox = rig.mail(("INBOX",))
    unclear = rig.mail(("INBOX", rig.finance, rig.travel))
    rig.gmail.mail_table[left_inbox].labels.discard("INBOX")
    rig.gmail.delete_mail(deleted)
    plan = rig.store.add_plan(
        [
            item(other_label, FINANCE, TRAVEL),
            item(deleted, FINANCE, TRAVEL),
            item(archived, FINANCE, TRAVEL),
            item(left_inbox, OTHER_ID, TRAVEL),
            item(unclear, FINANCE, TRAVEL),
        ]
    )

    await rig.apply().run_once()

    reasons = {r.item.message_id: (r.state, r.reason) for r in rig.store.plans[plan].items}
    assert reasons == {
        other_label: (ItemState.SKIPPED, SkipReason.CHANGED),
        deleted: (ItemState.SKIPPED, SkipReason.GONE),
        archived: (ItemState.SKIPPED, SkipReason.OUT_OF_SCOPE),
        left_inbox: (ItemState.SKIPPED, SkipReason.OUT_OF_SCOPE),
        unclear: (ItemState.SKIPPED, SkipReason.CHANGED),
    }
    assert rig.modifies() == 0


async def test_a_plan_with_a_category_that_left_the_list_is_cancelled_and_nothing_moves() -> None:
    """D20 replaces the old per-item skip: the whole plan is cancelled before any item is applied."""
    rig = ApplyRig()
    gone = "00000000-0000-0000-0000-0000000000ff"
    stale = rig.mail(("INBOX", rig.finance))
    fine = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(stale, FINANCE, gone), item(fine, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    assert rig.store.state(plan) is PlanState.CANCELLED
    assert rig.labels_of(stale) == {"INBOX", "Assistant/Finance"}
    assert rig.labels_of(fine) == {"INBOX", "Assistant/Finance"}  # nothing of a cancelled plan moves
    assert rig.modifies() == 0


async def test_a_category_that_leaves_the_list_during_the_apply_skips_the_item_not_the_plan() -> None:
    """Defence in depth: the batch re-checks the list for every item."""
    rig = ApplyRig()
    stale = rig.mail(("INBOX", rig.finance))
    fine = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(stale, FINANCE, TRAVEL), item(fine, FINANCE, FINANCE, None, NEWSLETTER)])
    original = rig.store.target_ids

    async def vanish(plan_id: object) -> frozenset[str]:
        found = await original(plan_id)  # type: ignore[arg-type]
        rig.store.categories.pop(TRAVEL)  # the list changes right after the plan-level check
        return found

    rig.store.target_ids = vanish  # type: ignore[method-assign]

    await rig.apply().run_once()

    assert rig.store.item(plan, stale).reason is SkipReason.CATEGORY_REMOVED
    assert rig.labels_of(stale) == {"INBOX", "Assistant/Finance"}
    assert rig.labels_of(fine) == {"INBOX", "Assistant/Finance", "Assistant/Newsletter"}


async def test_a_label_of_a_deleted_category_counts_as_the_old_label_of_other() -> None:
    rig = ApplyRig()
    legacy = rig.gmail.add_label("Assistant/Legacy")
    mid = rig.mail(("INBOX", legacy))
    rig.store.add_plan([item(mid, OTHER_ID, FINANCE)])

    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Assistant/Finance"}


async def test_pinned_mail_is_never_moved() -> None:
    rig = ApplyRig()
    pinned = rig.mail(("INBOX", rig.finance), sender="security@accounts.google.com", auth_results=GOOGLE_AUTH)
    plan = rig.store.add_plan([item(pinned, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    assert rig.store.item(plan, pinned).reason is SkipReason.PINNED
    assert rig.labels_of(pinned) == {"INBOX", "Assistant/Finance"}
    assert rig.modifies() == 0


async def test_the_result_notice_has_counts_offers_move_back_and_lock_and_names_empty_labels() -> None:
    rig = ApplyRig()
    a = rig.mail(("INBOX", rig.finance))
    b = rig.mail(("INBOX", rig.finance))
    stale = rig.mail(("INBOX", rig.travel))
    rig.gmail.mail_table[stale].labels.add(rig.finance)  # unclear: skipped
    plan = rig.store.add_plan([item(a, FINANCE, TRAVEL), item(b, FINANCE, TRAVEL), item(stale, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    assert rig.notifier.results == [(plan, (Offer.MOVE_BACK, Offer.LOCK))]
    text = rig.telegram.texts[-1]
    assert "2 moved" in text
    assert "1 skipped" in text
    assert "Finance" not in text  # Finance still holds the unclear mail


async def test_the_notice_names_a_label_that_is_empty_after_the_apply() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    rig.store.add_plan([item(mid, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    text = rig.telegram.texts[-1]
    assert "1 moved" in text
    assert "Finance" in text
    assert "now empty" in text
