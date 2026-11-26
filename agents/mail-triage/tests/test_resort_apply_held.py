"""RED-002: while the rename plan is not done a re-sort apply uses stored label ids only (R4, ADR-0061 point 1).

A target label without a stored id is never created or adopted: the item stays approved for a later run, it is not
counted as a failed attempt, and no Gmail write happens for it.
"""

from __future__ import annotations

import pytest

from app.core.resort_plan import ItemState, PlanState
from tests.resort_apply_support import FINANCE, OTHER_ID, TRAVEL, ApplyRig, item

_CREATES = ("labels.create", "labels.patch", "labels.delete")


@pytest.mark.parametrize("target", ["other", "unstored_category"])
async def test_given_a_target_without_a_stored_id_when_applied_then_no_label_is_made_and_mail_is_not_moved(
    target: str,
) -> None:
    rig = ApplyRig()
    rig.store.writes_held = True
    rig.store.stored_ids = {FINANCE: rig.finance}  # Travel and Other have no stored id yet
    mid = rig.mail(("INBOX", rig.finance))
    destination = OTHER_ID if target == "other" else TRAVEL
    if target == "other":  # a user label of the same name must not be adopted either
        rig.gmail.add_label("Other")
    else:
        rig.gmail.delete_label(rig.travel)
    plan = rig.store.add_plan([item(mid, FINANCE, destination)])
    labels_before = dict(rig.gmail.label_table)

    await rig.apply().run_once()

    assert rig.gmail.label_table == labels_before
    assert not [call for call in rig.gmail.calls if call in _CREATES]
    assert rig.modifies() == 0
    assert rig.labels_of(mid) == {"INBOX", "Finance"}
    assert rig.store.item(plan, mid).state is ItemState.APPROVED  # waits, never failed
    assert rig.store.attempts == {}
    assert rig.store.state(plan) is PlanState.APPLYING


async def test_given_a_held_plan_when_the_target_has_a_stored_id_then_the_mail_is_moved_by_id() -> None:
    rig = ApplyRig()
    rig.store.writes_held = True
    rig.store.stored_ids = {FINANCE: rig.finance, TRAVEL: rig.travel}
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)])

    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Travel"}
    assert rig.store.state(plan) is PlanState.APPLIED
    assert "labels.create" not in rig.gmail.calls


async def test_given_the_plan_is_done_when_the_target_has_no_id_then_the_label_is_made_as_before() -> None:
    rig = ApplyRig()
    rig.store.stored_ids = {FINANCE: rig.finance}
    mid = rig.mail(("INBOX", rig.finance))
    rig.store.add_plan([item(mid, FINANCE, OTHER_ID)])

    await rig.apply().run_once()

    assert rig.labels_of(mid) == {"INBOX", "Other"}
