"""U-label-structure-23, criteria 2, 4 and 6: apply and move back with real pairs, skips and removed targets.

ADR-0056 points 4 and 5, spec D13, D20, AC-47, AC-51. The audit row of a pair holds the label ids of the whole pair,
joined with commas (``label_ids``), so the apply, the retry and the move back work on sets of labels.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.resort_plan import ItemState, PlanState
from app.usecases.resort_apply import Offer, SkipReason, label_ids
from tests.resort_apply_support import FINANCE, NEWSLETTER, OTHER_ID, RECEIPT, TRAVEL, ApplyRig, item


async def test_given_a_pair_when_the_extra_label_changes_then_only_the_extra_label_swaps() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance, rig.newsletter))
    rig.store.add_plan([item(mid, FINANCE, FINANCE, NEWSLETTER, RECEIPT)])

    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Assistant/Finance", "Assistant/Receipt"}


async def test_given_a_pair_when_both_parts_change_then_both_labels_swap_and_the_audit_holds_the_pair() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance, rig.newsletter))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL, NEWSLETTER, RECEIPT)])

    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Assistant/Travel", "Assistant/Receipt"}
    (move,) = await rig.store.audit_moves(plan)
    assert label_ids(move.old_label) == {rig.finance, rig.newsletter}
    assert label_ids(move.new_label) == {rig.travel, rig.receipt}


async def test_given_a_pair_when_the_extra_label_is_added_or_dropped_then_the_topic_label_stays() -> None:
    rig = ApplyRig()
    added = rig.mail(("INBOX", rig.finance))
    dropped = rig.mail(("INBOX", rig.finance, rig.newsletter))
    unfiled = rig.mail(("INBOX",))
    rig.store.add_plan(
        [
            item(added, FINANCE, FINANCE, None, NEWSLETTER),
            item(dropped, FINANCE, FINANCE, NEWSLETTER, None),
            item(unfiled, OTHER_ID, TRAVEL, None, RECEIPT),
        ]
    )

    await rig.apply().run_once()

    assert rig.labels_of(added) == {"INBOX", "Assistant/Finance", "Assistant/Newsletter"}
    assert rig.labels_of(dropped) == {"INBOX", "Assistant/Finance"}
    assert rig.labels_of(unfiled) == {"INBOX", "Assistant/Travel", "Assistant/Receipt"}


async def test_given_the_user_changed_the_extra_label_meanwhile_when_applied_then_the_item_is_skipped() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance, rig.receipt))  # the plan expects Newsletter; the user chose Receipt
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL, NEWSLETTER, None)])

    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Assistant/Finance", "Assistant/Receipt"}  # untouched
    assert rig.store.item(plan, mid).state is ItemState.SKIPPED
    assert rig.store.item(plan, mid).reason is SkipReason.CHANGED


async def test_given_a_mail_moved_by_the_user_meanwhile_when_applied_then_it_is_skipped_and_shown_as_skipped() -> None:
    rig = ApplyRig()
    moved_by_user = rig.mail(("INBOX", rig.travel))  # the plan expected Finance
    untouched = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(moved_by_user, FINANCE, TRAVEL), item(untouched, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    assert rig.store.item(plan, moved_by_user).reason is SkipReason.CHANGED
    assert rig.labels_of(moved_by_user) == {"INBOX", "Assistant/Travel"}
    assert rig.labels_of(untouched) == {"INBOX", "Assistant/Travel"}
    assert any("1 moved, 1 skipped" in text for text in rig.telegram.texts)


async def test_given_the_new_extra_category_left_the_list_when_applied_then_the_item_is_skipped() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, FINANCE, None, NEWSLETTER)])
    rig.store.categories.pop(NEWSLETTER)  # the target is no longer in the list; the plan is cancelled first

    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Assistant/Finance"}
    assert rig.store.state(plan) is PlanState.CANCELLED


async def test_given_an_applied_pair_plan_when_moved_back_then_the_old_pair_is_restored() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance, rig.newsletter))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL, NEWSLETTER, RECEIPT)])
    await rig.apply().run_once()
    rig.store.request_move_back(plan)

    await rig.move_back().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Assistant/Finance", "Assistant/Newsletter"}
    assert len(rig.store.restores) == 1


async def test_given_an_applied_pair_when_the_user_added_a_label_meanwhile_then_move_back_leaves_the_mail() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance, rig.newsletter))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL, NEWSLETTER, RECEIPT)])
    await rig.apply().run_once()
    rig.gmail.mail_table[mid].labels.add(rig.finance)  # the user adds a second topic label
    rig.store.request_move_back(plan)

    await rig.move_back().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Assistant/Travel", "Assistant/Receipt", "Assistant/Finance"}
    assert rig.store.restores == []


async def test_given_an_approved_plan_when_the_delay_has_not_passed_then_nothing_moves_and_after_it_the_items_do() -> (
    None
):
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance, rig.newsletter))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL, NEWSLETTER, RECEIPT)], apply_after=timedelta(minutes=15))

    await rig.apply().run_once()
    assert rig.modifies() == 0
    assert rig.store.state(plan) is PlanState.SCHEDULED
    assert rig.telegram.texts == []

    rig.clock.advance(timedelta(minutes=15))
    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Assistant/Travel", "Assistant/Receipt"}
    (text,) = rig.telegram.texts
    assert "1 moved, 0 skipped" in text
    assert "lock web sign-in" in text.lower()
    assert "/web_unlock" in text  # the line that says what Lock does
    assert rig.notifier.results == [(plan, (Offer.MOVE_BACK, Offer.LOCK))]


async def test_given_a_plan_whose_target_category_was_removed_when_the_apply_runs_then_it_is_cancelled() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)], apply_after=timedelta(minutes=15))
    rig.store.categories.pop(TRAVEL)  # an upload removed the category the plan moves mail into
    rig.clock.advance(timedelta(minutes=15))

    await rig.apply().run_once()

    assert rig.store.state(plan) is PlanState.CANCELLED
    assert rig.modifies() == 0  # no item went to a deleted label
    assert rig.labels_of(mid) == {"INBOX", "Assistant/Finance"}
    assert any("cancelled" in text for text in rig.telegram.texts)


async def test_given_a_list_save_that_keeps_the_targets_when_a_plan_is_scheduled_then_it_finishes() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])
    rig.store.categories[RECEIPT] = "Receipt, renamed"  # another category changed; the plan's targets are all there

    await rig.apply().run_once()

    assert rig.store.state(plan) is PlanState.APPLIED
    assert rig.labels_of(mid) == {"INBOX", "Assistant/Travel"}
