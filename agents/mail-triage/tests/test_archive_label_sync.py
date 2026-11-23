"""U-label-structure-18, criteria 1 to 3 (ADR-0059): the sync adopts, creates and renames the archive label."""

from __future__ import annotations

from app.adapters.gmail_resort import GmailResort
from app.core.scope import ArchiveLabel, Scope, classify
from app.usecases.list_sync import ArchiveNames, ListSync
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.list_store import FakeListStore


def make(gmail: FakeGmail, store: FakeListStore, archive: ArchiveLabel | None = None) -> tuple[ListSync, ArchiveLabel]:
    ref = archive or ArchiveLabel("Archive")
    return ListSync(GmailResort(gmail, ref, sleep=lambda _s: None), store, ref), ref


def store_with(wanted: str, applied: str | None) -> FakeListStore:
    store = FakeListStore()
    store.archive = ArchiveNames(wanted=wanted, applied=applied)
    return store


async def test_given_a_first_time_name_and_an_existing_label_when_the_sync_runs_then_it_is_adopted() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Bewaard")
    mail = gmail.add_mail(labels=(label,))
    sync, ref = make(gmail, store_with("Bewaard", None))

    await sync.run()

    assert gmail.label_names().count("Bewaard") == 1
    assert (ref.name, ref.label_id) == ("Bewaard", label)
    assert gmail.mail_table[mail].labels == {label}
    assert "labels.patch" not in gmail.calls


async def test_given_a_first_time_name_and_no_such_label_when_the_sync_runs_then_it_is_created() -> None:
    gmail = FakeGmail()
    sync, ref = make(gmail, store_with("Mail/Done", None))

    await sync.run()

    assert gmail.label_names().count("Mail/Done") == 1
    assert (ref.name, ref.label_id) == ("Mail/Done", gmail.label_id("Mail/Done"))


async def test_given_a_later_change_of_the_name_when_synced_then_the_label_is_renamed_by_id_and_protected() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Bewaard")
    mail = gmail.add_mail(labels=(label, "INBOX"))
    sync, ref = make(gmail, store_with("Mail/Done", "Bewaard"), ArchiveLabel("Bewaard"))

    await sync.run()

    assert gmail.label_table[label] == "Mail/Done"
    assert [n for n in gmail.label_names() if n in {"Bewaard", "Mail/Done"}] == ["Mail/Done"]  # no second label
    assert label in gmail.mail_table[mail].labels  # no mail moved into or out of it
    assert (ref.name, ref.label_id) == ("Mail/Done", label)
    names = {gmail.label_table[i] for i in gmail.mail_table[mail].labels}
    assert classify(names, ref.name, ()) is Scope.OUT


async def test_given_a_change_while_a_plan_is_in_flight_when_synced_then_the_rename_waits_for_it() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Bewaard")
    store = store_with("Mail/Done", "Bewaard")
    store.save_list(["Bills"])
    store.plan_open = True
    sync, ref = make(gmail, store, ArchiveLabel("Bewaard"))

    result = await sync.run()

    assert gmail.label_table[label] == "Bewaard"
    assert ref.name == "Bewaard"
    assert store.cursor_version == 0  # not done: the next run looks at the name again
    assert "Assistant/Bills" in gmail.label_names()  # the rest of the sync goes on
    assert result.waiting is True

    store.plan_open = False  # the plan is terminal
    result = await sync.run()

    assert gmail.label_table[label] == "Mail/Done"
    assert ref.name == "Mail/Done"
    assert store.cursor_version == store.version
    assert result.waiting is False


async def test_given_a_change_and_the_old_label_is_gone_when_the_sync_runs_then_the_new_one_is_created_once() -> None:
    gmail = FakeGmail()
    sync, ref = make(gmail, store_with("Mail/Done", "Bewaard"), ArchiveLabel("Bewaard"))

    await sync.run()
    await sync.run()

    assert gmail.label_names().count("Mail/Done") == 1
    assert ref.name == "Mail/Done"


async def test_given_the_rename_was_done_but_the_cursor_not_when_the_sync_repeats_then_the_label_is_adopted() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Mail/Done")  # renamed by the earlier run that then crashed
    sync, ref = make(gmail, store_with("Mail/Done", "Bewaard"), ArchiveLabel("Bewaard"))

    await sync.run()

    assert ref.label_id == label
    assert "labels.patch" not in gmail.calls
    assert gmail.label_names().count("Mail/Done") == 1


async def test_given_a_new_name_another_label_has_when_synced_then_nothing_is_renamed_and_it_is_not_done() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Bewaard")
    gmail.add_label("Mail/Done")  # a different, user-owned label
    store = store_with("Mail/Done", "Bewaard")
    sync, ref = make(gmail, store, ArchiveLabel("Bewaard"))

    result = await sync.run()

    assert gmail.label_table[old] == "Bewaard"
    assert ref.name == "Bewaard"  # the old label stays the protected one
    assert result.failed == 1
    assert store.cursor_version == 0


async def test_given_an_unchanged_name_in_another_case_when_the_sync_runs_then_the_label_is_not_renamed() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("archive")
    sync, ref = make(gmail, store_with("Archive", "Archive"), ArchiveLabel("Archive"))

    await sync.run()

    assert gmail.label_table[label] == "archive"
    assert ref.label_id == label
    assert "labels.patch" not in gmail.calls
