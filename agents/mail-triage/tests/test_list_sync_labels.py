"""U-mail-categories-06, criteria 1 to 3 and 6 to 7: the label sync (AC-25, AC-40, AC-49, AC-53)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.gmail_resort import GmailResort
from app.core.scope import ArchiveLabel
from app.db.models import OTHER_ID
from app.usecases.list_sync import ArchiveNames, ListSync
from category_policy import MAX_CATEGORIES
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.list_store import FakeListStore

if TYPE_CHECKING:
    import uuid


def make(gmail: FakeGmail, store: FakeListStore) -> ListSync:
    ref = ArchiveLabel("Archive")
    return ListSync(GmailResort(gmail, ref, sleep=lambda _s: None), store, ref)


def modifies(gmail: FakeGmail) -> list[str]:
    return [c for c in gmail.calls if c == "messages.modify"]


async def test_given_a_gmail_without_archive_when_the_sync_runs_then_it_exists_and_no_mail_is_filed_in_it() -> None:
    gmail = FakeGmail()
    gmail.add_mail()

    await make(gmail, FakeListStore()).run()

    assert gmail.label_names().count("Archive") == 1
    assert modifies(gmail) == []
    assert gmail.mail_table["m1"].labels == {"INBOX"}


@pytest.mark.parametrize("existing", ["Archive", "archive"])
async def test_given_an_archive_label_when_the_sync_runs_then_it_is_left_alone(existing: str) -> None:
    gmail = FakeGmail()
    gmail.add_label(existing)

    await make(gmail, FakeListStore()).run()

    assert [n for n in gmail.label_names() if n.casefold() == "archive"] == [existing]
    assert "labels.patch" not in gmail.calls


async def test_given_archive_was_deleted_when_the_sync_runs_again_then_it_is_made_again() -> None:
    gmail = FakeGmail()
    sync = make(gmail, FakeListStore())
    await sync.run()
    gmail.delete_label(gmail.label_id("Archive"))

    await sync.run()

    assert gmail.label_names().count("Archive") == 1


async def test_given_two_overlapping_runs_when_both_make_archive_then_it_exists_once() -> None:
    gmail = FakeGmail()
    gmail.race_on_create("Archive")

    # the first create loses to an overlapping run (409); the second run then finds the label
    await make(gmail, FakeListStore()).run()
    await make(gmail, FakeListStore()).run()

    assert gmail.label_names().count("Archive") == 1


async def test_given_a_first_start_when_the_sync_runs_then_version_one_is_seeded_from_the_current_labels() -> None:
    gmail = FakeGmail()
    for name in (
        "Assistant/Travel",
        "Assistant/Bills",
        "Assistant/Other",
        "Assistant/Old/Nested",
        "Assistant//Bad",
        "Archive/x",
        "Work",
    ):
        gmail.add_label(name)
    store = FakeListStore()

    result = await make(gmail, store).run()

    # sorted; Other is built in; nested names are categories (v2); foreign and malformed labels stay out
    assert store.seeded == [("Bills", "Old/Nested", "Travel")]
    assert (result.version, store.version, store.cursor_version) == (1, 1, 1)
    assert [c.name for c in store.categories] == ["Bills", "Old/Nested", "Travel"]


async def test_given_no_labels_at_all_when_the_first_sync_runs_then_an_empty_version_one_exists() -> None:
    store = FakeListStore()

    await make(FakeGmail(), store).run()

    assert (store.version, store.categories, store.cursor_version) == (1, (), 1)


async def test_given_more_labels_than_the_cap_or_unfit_names_when_seeded_then_only_fit_ones_are_listed() -> None:
    gmail = FakeGmail()
    for number in range(MAX_CATEGORIES + 5):
        gmail.add_label(f"Assistant/C{number:02d}")
    gmail.add_label("Assistant/" + "x" * 41)
    gmail.add_label("Assistant/Archive")
    store = FakeListStore()

    await make(gmail, store).run()

    assert len(store.categories) == MAX_CATEGORIES
    assert all(c.name not in {"Archive", "x" * 41} for c in store.categories)
    assert "Assistant/Archive" in store.label_names  # not lost: it is shown as an older label


async def test_given_a_second_start_when_the_list_exists_then_it_is_not_seeded_again() -> None:
    gmail = FakeGmail()
    gmail.add_label("Assistant/Bills")
    store = FakeListStore()
    sync = make(gmail, store)

    await sync.run()
    await sync.run()

    assert len(store.seeded) == 1


async def test_given_categories_without_labels_when_the_sync_runs_then_the_labels_are_made_once_and_remembered() -> (
    None
):
    gmail = FakeGmail()
    store = FakeListStore()
    ids = store.save_list(["Bills", "Travel"])

    await make(gmail, store).run()
    await make(gmail, store).run()

    assert gmail.label_names().count("Assistant/Bills") == 1
    assert "Assistant/Other" in gmail.label_names()
    assert store.labels[ids["Bills"]].label_name == "Assistant/Bills"
    assert gmail.label_table[store.labels[ids["Bills"]].label_id] == "Assistant/Bills"
    assert "labels.patch" not in gmail.calls


async def _synced(gmail: FakeGmail, store: FakeListStore, name: str) -> tuple[uuid.UUID, str]:
    """A list with one category whose label was made by an earlier sync, and one mail under that label."""
    ids = store.save_list([name])
    sync = make(gmail, store)
    await sync.run()
    return ids[name], store.labels[ids[name]].label_id


async def test_given_a_name_only_change_when_the_sync_runs_then_the_label_is_renamed_by_id_without_mail_or_model() -> (
    None
):
    gmail = FakeGmail()
    store = FakeListStore()
    category, label = await _synced(gmail, store, "Bills")
    mail = gmail.add_mail(labels=(label,))
    store.save_list(["Invoices"], keep={"Invoices": category})
    gmail.calls.clear()

    await make(gmail, store).run()

    assert gmail.label_table[label] == "Assistant/Invoices"
    assert gmail.calls.count("labels.patch") == 1
    assert not [c for c in gmail.calls if c.startswith("messages.")]  # no mail read or changed, no model involved
    assert gmail.mail_table[mail].labels == {label}
    assert store.labels[category].label_id == label
    assert store.labels[category].label_name == "Assistant/Invoices"
    assert store.counts[category] == 1  # the count of the label survives the rename
    assert store.cursor_version == 2


async def test_given_a_crash_after_the_rename_when_the_run_repeats_then_nothing_is_done_twice() -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    category, _ = await _synced(gmail, store, "Bills")
    store.save_list(["Invoices"], keep={"Invoices": category})
    store.crash_before_cursor = True
    sync = make(gmail, store)

    with pytest.raises(ConnectionResetError):
        await sync.run()
    assert store.cursor_version == 1
    gmail.calls.clear()
    await sync.run()

    assert "labels.patch" not in gmail.calls
    assert "labels.create" not in gmail.calls
    assert gmail.label_names().count("Assistant/Invoices") == 1
    assert store.cursor_version == 2


async def test_given_a_rename_done_in_gmail_but_not_remembered_when_it_repeats_then_it_is_not_renamed_again() -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    category, label = await _synced(gmail, store, "Bills")
    store.save_list(["Invoices"], keep={"Invoices": category})
    gmail.label_table[label] = "Assistant/Invoices"  # Gmail did it; the database still says Bills
    gmail.calls.clear()

    await make(gmail, store).run()

    assert "labels.patch" not in gmail.calls
    assert store.labels[category].label_name == "Assistant/Invoices"


async def test_given_a_rename_onto_a_taken_name_when_synced_then_the_rest_is_done_and_the_cursor_waits() -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    first, first_label = await _synced(gmail, store, "Bills")
    store.save_list(["Invoices", "Travel"], keep={"Invoices": first})
    gmail.add_label("Assistant/Invoices")  # made by the user after the save was accepted

    result = await make(gmail, store).run()

    assert gmail.label_table[first_label] == "Assistant/Bills"
    assert "Assistant/Travel" in gmail.label_names()
    assert result.failed == 1
    assert store.cursor_version == 1


async def test_given_the_user_deleted_a_category_label_in_gmail_when_the_sync_runs_then_it_is_made_again() -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    category, label = await _synced(gmail, store, "Bills")
    gmail.delete_label(label)

    await make(gmail, store).run()

    assert gmail.label_names().count("Assistant/Bills") == 1
    assert store.labels[category].label_id != label
    assert store.labels[category].label_id == gmail.label_id("Assistant/Bills")


async def test_given_an_older_label_not_on_the_list_when_the_sync_runs_then_it_is_listed_and_its_mail_keeps_it() -> (
    None
):
    gmail = FakeGmail()
    store = FakeListStore()
    store.save_list(["Bills"])
    old = gmail.add_label("Assistant/Old stuff")
    mail = gmail.add_mail(labels=(old,))

    await make(gmail, store).run()

    assert "Assistant/Old stuff" in store.label_names
    assert {"Assistant/Bills", "Assistant/Other"} <= set(store.label_names)
    assert gmail.mail_table[mail].labels == {old}
    assert gmail.label_table[old] == "Assistant/Old stuff"


async def test_given_labelled_mail_when_the_sync_runs_then_counts_are_kept_per_category_and_for_other() -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    ids = store.save_list(["Bills", "Travel"])
    bills = gmail.add_label("Assistant/Bills")
    other = gmail.add_label("Assistant/Other")
    gmail.add_mail(labels=(bills,))
    gmail.add_mail(labels=(bills,))
    gmail.add_mail(labels=(other,))

    await make(gmail, store).run()

    assert store.counts == {ids["Bills"]: 2, ids["Travel"]: 0, OTHER_ID: 1}


@pytest.mark.parametrize("archive", ["Assistant/Archive", "Bewaard"])
async def test_given_a_configured_archive_label_when_the_sync_runs_then_that_label_is_made_once_and_not_a_category(
    archive: str,
) -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    store.archive = ArchiveNames(wanted=archive, applied=None)
    ref = ArchiveLabel(archive)
    sync = ListSync(GmailResort(gmail, ref, sleep=lambda _s: None), store, ref)

    await sync.run()
    await sync.run()

    assert gmail.label_names().count(archive) == 1
    assert "Archive" not in gmail.label_names()
    assert all(c.name.casefold() != "archive" for c in store.categories)


async def test_given_the_default_archive_label_exists_when_the_list_is_seeded_then_it_is_not_a_category() -> None:
    gmail = FakeGmail()
    gmail.add_label("Assistant/Archive")
    gmail.add_label("Assistant/Travel")
    store = FakeListStore()
    store.archive = ArchiveNames(wanted="Assistant/Archive", applied=None)
    ref = ArchiveLabel("Assistant/Archive")

    await ListSync(GmailResort(gmail, ref, sleep=lambda _s: None), store, ref).run()

    assert store.seeded == [("Travel",)]
