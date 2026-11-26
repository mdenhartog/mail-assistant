"""U-mail-categories-15, criterion 8: Move back restores the old labels from the audit, once per plan (AC-41, AC-57)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from app.core.resort_plan import PlanState
from tests.resort_apply_support import FINANCE, OTHER_ID, TRAVEL, ApplyRig, item

if TYPE_CHECKING:
    import uuid


async def _applied(rig: ApplyRig) -> tuple[str, str, str, uuid.UUID]:
    a = rig.mail(("INBOX", rig.finance))
    unfiled = rig.mail(("INBOX",))
    changed = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan(
        [item(a, FINANCE, TRAVEL), item(unfiled, OTHER_ID, TRAVEL), item(changed, FINANCE, TRAVEL)]
    )
    await rig.apply().run_once()
    rig.telegram.texts.clear()
    return a, unfiled, changed, plan


async def test_move_back_restores_old_labels_skips_changed_mail_and_sends_one_notice() -> None:
    rig = ApplyRig()
    a, unfiled, changed, plan = await _applied(rig)
    mine = rig.gmail.add_label("Mine")
    rig.gmail.mail_table[changed].labels.discard(rig.travel)  # the user moved it on to another label
    rig.gmail.mail_table[changed].labels.add(mine)
    rig.store.request_move_back(plan)

    await rig.move_back().run_once()

    assert rig.labels_of(a) == {"INBOX", "Finance"}
    assert rig.labels_of(unfiled) == {"INBOX"}  # it had no label: only the new one goes
    assert rig.labels_of(changed) == {"INBOX", "Mine"}
    assert len(rig.telegram.texts) == 1
    assert "2 restored" in rig.telegram.texts[0]
    assert "1 skipped" in rig.telegram.texts[0]
    assert {m.message_id for _, m, _ in rig.store.restores} == {a, unfiled}
    assert {c for _, _, c in rig.store.restores} == {"web"}


async def test_move_back_runs_once_per_plan_even_when_repeated_or_concurrent() -> None:
    rig = ApplyRig()
    *_, plan = await _applied(rig)
    rig.store.request_move_back(plan)

    await asyncio.gather(rig.move_back().run_once(), rig.move_back().run_once())
    await rig.move_back().run_once()

    assert len(rig.telegram.texts) == 1


async def test_move_back_does_not_restore_a_label_that_left_the_list_because_it_is_not_managed_any_more() -> None:
    rig = ApplyRig()
    a, *_, plan = await _applied(rig)
    del rig.store.categories[FINANCE]  # the category left the list: its label is no longer managed (ADR-0060)
    rig.store.request_move_back(plan)
    rig.mailbox.writes.clear()

    await rig.move_back().run_once()

    assert rig.labels_of(a) == {"INBOX", "Travel"}  # left as it is, not half restored
    assert a not in {m.message_id for _, m, _ in rig.store.restores}


async def test_move_back_looks_at_managed_labels_only_and_keeps_the_label_of_the_user() -> None:
    rig = ApplyRig()
    a, unfiled, changed, plan = await _applied(rig)
    folder = rig.gmail.add_label("Amerika")
    rig.gmail.mail_table[a].labels.add(folder)  # the user filed it in their own label after the apply
    rig.store.request_move_back(plan)
    rig.mailbox.writes.clear()

    await rig.move_back().run_once()

    assert rig.labels_of(a) == {"INBOX", "Finance", "Amerika"}
    managed_ids = {rig.finance, rig.travel}
    assert {label_id for _, _, label_id in rig.mailbox.writes} <= managed_ids
    assert rig.labels_of(changed) == {"INBOX", "Finance"}
    assert rig.labels_of(unfiled) == {"INBOX"}


async def test_move_back_leaves_a_mail_alone_that_was_archived_after_the_apply() -> None:
    rig = ApplyRig()
    a, _unfiled, _changed, plan = await _applied(rig)
    archive = rig.gmail.add_label("Archive")
    rig.gmail.mail_table[a].labels.add(archive)
    rig.store.request_move_back(plan)
    rig.mailbox.writes.clear()

    await rig.move_back().run_once()

    assert rig.labels_of(a) == {"INBOX", "Travel", "Archive"}
    assert not [w for w in rig.mailbox.writes if w[1] == a]
    assert a not in {m.message_id for _, m, _ in rig.store.restores}


async def test_move_back_only_processes_an_applied_plan() -> None:
    rig = ApplyRig()
    mid = rig.mail(("INBOX", rig.finance))
    plan = rig.store.add_plan([item(mid, FINANCE, TRAVEL)], state=PlanState.SCHEDULED)
    rig.store.request_move_back(plan)

    await rig.move_back().run_once()

    assert rig.telegram.texts == []
    assert plan not in rig.store.processed


async def test_a_crash_between_the_two_restore_calls_is_finished_on_retry() -> None:
    rig = ApplyRig()
    a, *_, plan = await _applied(rig)
    rig.store.request_move_back(plan)

    def crash(_mid: str) -> None:
        raise ConnectionResetError

    rig.mailbox.on_remove = crash
    with pytest.raises(ConnectionResetError):
        await rig.move_back().run_once()
    assert rig.labels_of(a) == {"INBOX", "Finance", "Travel"}
    rig.mailbox.on_remove = None
    rig.clock.advance(timedelta(minutes=6))

    await rig.move_back().run_once()

    assert rig.labels_of(a) == {"INBOX", "Finance"}
    assert len(rig.telegram.texts) == 1


async def test_move_back_stops_while_web_sign_in_is_locked() -> None:
    rig = ApplyRig()
    a, *_, plan = await _applied(rig)
    rig.store.request_move_back(plan)
    rig.lock.locked = True

    await rig.move_back().run_once()

    assert rig.labels_of(a) == {"INBOX", "Travel"}
    assert rig.telegram.texts == []
