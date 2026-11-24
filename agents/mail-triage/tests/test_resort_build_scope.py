"""INT-010 U-18: which mail a re-sort build plans: the inbox or a managed label, decided by label id (AC 2, 3)."""

from __future__ import annotations

import pytest

from app.core.judgement import OTHER_ID
from tests.resort_build_support import FINANCE, TRAVEL, Rig


async def test_only_mail_of_the_inbox_or_a_managed_label_is_planned_even_when_the_listing_is_wide() -> None:
    rig = Rig()
    rig.request()
    folder = rig.gmail.add_label("Receipts 2019")  # the user's own label: not managed
    rig.mailbox.listed_names.add("Receipts 2019")  # a listing that returns it anyway
    inbox = rig.gmail.add_mail(("INBOX",), subject="inbox")
    managed = rig.gmail.add_mail((rig.finance_label,), subject="managed")
    rig.gmail.add_mail((folder,), subject="folder")
    kept = rig.gmail.add_mail(("INBOX", folder), subject="inbox-and-folder")  # in the inbox: in scope, folder kept
    rig.judge.answer = TRAVEL

    await rig.build.run_once()

    planned = {i.message_id for i in rig.store.items_of(rig.store.plan())}
    assert planned == {inbox, managed, kept}
    assert "folder" not in rig.judge.subjects


async def test_a_label_is_managed_by_its_stored_id_not_by_its_current_name() -> None:
    rig = Rig()
    rig.request()
    rig.store.stored_ids[FINANCE] = rig.finance_label
    rig.gmail.label_table[rig.finance_label] = "Bills"  # the user renamed it by hand
    rig.mailbox.listed_names.add("Bills")
    renamed = rig.gmail.add_mail((rig.finance_label,), subject="renamed")
    look_alike = rig.gmail.add_label("Finance")  # another label that carries the old name
    rig.mailbox.listed_names.add("Finance")
    stranger = rig.gmail.add_mail((look_alike,), subject="stranger")
    rig.judge.answer = TRAVEL

    await rig.build.run_once()

    planned = {i.message_id for i in rig.store.items_of(rig.store.plan())}
    assert planned == {renamed}
    assert stranger not in planned


async def test_the_archive_label_wins_over_a_managed_label() -> None:
    rig = Rig()
    rig.request()
    archive = rig.gmail.add_label("Archive")
    rig.mailbox.listed_names.add("Archive")
    rig.gmail.add_mail((archive, rig.finance_label), subject="archived")
    rig.gmail.add_mail(("INBOX", archive), subject="archived-in-inbox")
    rig.judge.answer = TRAVEL

    await rig.build.run_once()

    plan = rig.store.plan()
    assert rig.store.items_of(plan) == []
    assert (plan.checked, rig.judge.calls) == (0, 0)


async def test_a_renamed_archive_label_still_wins() -> None:
    rig = Rig()
    rig.request()
    archive = rig.gmail.add_label("Done")
    rig.store.stored_ids["archive"] = archive  # the archive setting was Archive; the user renamed it by hand
    rig.mailbox.listed_names.add("Done")
    rig.gmail.add_mail((archive, rig.finance_label), subject="archived")
    rig.judge.answer = TRAVEL

    await rig.build.run_once()

    assert rig.store.items_of(rig.store.plan()) == []
    assert rig.judge.calls == 0


async def test_mail_under_the_other_label_is_filed_from_other() -> None:
    rig = Rig()
    rig.request()
    other = rig.gmail.add_label("Other")
    mid = rig.gmail.add_mail(("INBOX", other), subject="sorted-later")
    rig.judge.answer = FINANCE

    await rig.build.run_once()

    (planned,) = rig.store.items_of(rig.store.plan())
    assert (planned.message_id, str(planned.old_topic_id)) == (mid, OTHER_ID)


@pytest.mark.parametrize("name", ["Misc", "Everything else"])
async def test_the_other_setting_decides_which_label_is_other(name: str) -> None:
    rig = Rig()
    rig.request()
    rig.store.other_name = name
    other = rig.gmail.add_label(name)
    old_default = rig.gmail.add_label("Other")  # the default name is only a label now: not managed
    rig.mailbox.listed_names.add(name)
    rig.mailbox.listed_names.add("Other")
    mid = rig.gmail.add_mail((other,), subject="in-other")
    rig.gmail.add_mail((old_default,), subject="stale-other")
    rig.judge.answer = FINANCE

    await rig.build.run_once()

    (planned,) = rig.store.items_of(rig.store.plan())
    assert (planned.message_id, str(planned.old_topic_id)) == (mid, OTHER_ID)
