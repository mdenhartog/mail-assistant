"""U-label-prefix-removal-05: the label sync works on managed labels by id (AC 12, 14, 19, 25; ADR-0060, ADR-0061).

The list is the boundary: nothing is seeded from Gmail, nothing is written to Gmail until the one-off rename plan is
``done``, and a managed label is found, adopted or renamed by id.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from app.adapters.gmail_resort import GmailLabelError, GmailResort
from app.core.managed import ManagedSet
from app.db.models import OTHER_ID
from app.usecases.list_sync import LabelKey, LabelSettings, ListSync, MigrationState
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.list_store import FakeListStore

if TYPE_CHECKING:
    import uuid

WRITES = ("labels.create", "labels.patch", "messages.modify")
OTHER = LabelKey("other")
ARCHIVE = LabelKey("archive")


def make(gmail: FakeGmail, store: FakeListStore) -> ListSync:
    return ListSync(GmailResort(gmail, ManagedSet(()), sleep=lambda _s: None), store)


def done() -> FakeListStore:
    return FakeListStore(migration=MigrationState.DONE)


def writes(gmail: FakeGmail) -> list[str]:
    return [call for call in gmail.calls if call in WRITES]


def category(store: FakeListStore, category_id: uuid.UUID) -> LabelKey:
    return LabelKey("category", category_id)


async def test_given_a_first_start_without_a_list_when_synced_then_nothing_is_seeded_from_gmail() -> None:
    gmail = FakeGmail()
    gmail.add_label("Work")
    gmail.add_label("Bills")
    store = done()

    result = await make(gmail, store).run()

    assert (store.version, store.categories, result.version) == (0, (), 0)  # waits for the upload
    assert not hasattr(store, "seed")


@pytest.mark.parametrize("state", [MigrationState.PENDING, MigrationState.CONFIRMED])
async def test_given_the_rename_plan_is_not_done_when_synced_then_no_label_write_is_made(state: MigrationState) -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Assistant/Bills")
    gmail.add_mail(labels=(old,))
    store = FakeListStore(migration=state)
    store.save_list(["Bills"])

    result = await make(gmail, store).run()

    assert writes(gmail) == []
    assert gmail.label_names().count("Assistant/Bills") == 1
    assert store.managed == {}
    assert (store.cursor_version, result.held) == (0, True)  # nothing was done, so nothing is marked as done


async def test_given_no_state_and_an_old_label_when_synced_then_it_starts_pending_and_writes_nothing() -> None:
    gmail = FakeGmail()
    gmail.add_label("Assistant/Bills")
    store = FakeListStore()
    store.save_list(["Bills"])

    await make(gmail, store).run()
    await make(gmail, store).run()

    assert store.migration_starts == [MigrationState.PENDING]
    assert writes(gmail) == []


async def test_given_a_mailbox_without_a_state_and_no_old_label_when_synced_then_it_starts_done_and_syncs() -> None:
    gmail = FakeGmail()
    gmail.add_label("Work")
    store = FakeListStore()
    store.save_list(["Bills"])

    await make(gmail, store).run()

    assert store.migration_starts == [MigrationState.DONE]
    assert {"Bills", "Other", "Archive"} <= set(gmail.label_names())


async def test_given_the_default_names_on_a_new_installation_when_synced_then_other_and_archive_exist() -> None:
    gmail = FakeGmail()
    store = done()
    ids = store.save_list(["Bills"])

    await make(gmail, store).run()

    assert {"Bills", "Other", "Archive"} <= set(gmail.label_names())
    assert gmail.label_table[store.managed[OTHER].label_id] == "Other"
    assert gmail.label_table[store.managed[ARCHIVE].label_id] == "Archive"
    assert gmail.label_table[store.managed[category(store, ids["Bills"])].label_id] == "Bills"
    assert "Assistant/Other" not in gmail.label_names()


async def test_given_the_user_changed_the_name_of_other_when_synced_then_it_is_renamed_by_id_and_the_id_is_kept() -> (
    None
):
    gmail = FakeGmail()
    store = done()
    store.save_list(["Bills"])
    await make(gmail, store).run()
    other_id = store.managed[OTHER].label_id
    mail = gmail.add_mail(labels=(other_id,))
    store.settings = LabelSettings(other="Overig", archive="Archive")
    gmail.calls.clear()

    await make(gmail, store).run()

    assert gmail.label_table[other_id] == "Overig"
    assert store.managed[OTHER].label_id == other_id
    assert store.managed[OTHER].label_name == "Overig"
    assert gmail.calls.count("labels.patch") == 1
    assert gmail.mail_table[mail].labels == {other_id}
    assert gmail.label_names().count("Overig") == 1


async def test_given_the_archive_name_was_changed_when_synced_then_the_label_is_renamed_by_id() -> None:
    gmail = FakeGmail()
    store = done()
    await make(gmail, store).run()
    archive_id = store.managed[ARCHIVE].label_id
    store.settings = LabelSettings(other="Other", archive="Bewaard/2026")

    await make(gmail, store).run()

    assert gmail.label_table[archive_id] == "Bewaard/2026"
    assert store.managed[ARCHIVE].label_id == archive_id


async def test_given_a_category_is_renamed_in_the_list_when_the_plan_is_done_then_its_label_is_renamed_by_id() -> None:
    gmail = FakeGmail()
    store = done()
    ids = store.save_list(["Bills"])
    await make(gmail, store).run()
    label = store.managed[category(store, ids["Bills"])].label_id
    mail = gmail.add_mail(labels=(label,))
    store.save_list(["Invoices"], keep={"Invoices": ids["Bills"]})
    gmail.calls.clear()

    await make(gmail, store).run()

    assert gmail.label_table[label] == "Invoices"
    assert gmail.calls.count("labels.patch") == 1
    assert store.managed[category(store, ids["Bills"])].label_id == label
    assert store.counts[ids["Bills"]] == 1
    assert gmail.mail_table[mail].labels == {label}
    assert store.cursor_version == 2


@pytest.mark.parametrize("existing", ["Bills", "bills"])
async def test_given_a_name_equal_to_a_label_of_the_user_when_synced_twice_then_it_is_adopted_and_nothing_changes(
    existing: str,
) -> None:
    gmail = FakeGmail()
    label = gmail.add_label(existing)
    mail = gmail.add_mail(labels=(label,))
    store = done()
    ids = store.save_list(["Bills"])

    await make(gmail, store).run()
    gmail.calls.clear()
    await make(gmail, store).run()

    assert store.managed[category(store, ids["Bills"])].label_id == label
    assert gmail.label_table[label] == existing  # the user's name stays
    assert [n.casefold() for n in gmail.label_names()].count("bills") == 1
    assert writes(gmail) == []
    assert gmail.mail_table[mail].labels == {label}


async def test_given_a_rename_onto_the_name_of_another_label_when_synced_then_that_label_is_adopted() -> None:
    gmail = FakeGmail()
    store = done()
    ids = store.save_list(["Bills"])
    await make(gmail, store).run()
    first = store.managed[category(store, ids["Bills"])].label_id
    other = gmail.add_label("Invoices")  # the user made it before the list was saved
    store.save_list(["Invoices"], keep={"Invoices": ids["Bills"]})

    result = await make(gmail, store).run()

    assert store.managed[category(store, ids["Bills"])].label_id == other
    assert gmail.label_table[first] == "Bills"  # left as it is: no longer managed
    assert result.failed == 0


async def test_given_the_user_deleted_a_managed_label_when_synced_then_it_is_made_again_and_the_new_id_stored() -> None:
    gmail = FakeGmail()
    store = done()
    ids = store.save_list(["Bills"])
    await make(gmail, store).run()
    old = store.managed[category(store, ids["Bills"])].label_id
    gmail.delete_label(old)

    await make(gmail, store).run()

    new = store.managed[category(store, ids["Bills"])].label_id
    assert new != old
    assert gmail.label_table[new] == "Bills"


async def test_given_labelled_mail_when_the_counts_are_refreshed_then_they_are_by_managed_id_without_mail_data() -> (
    None
):
    gmail = FakeGmail()
    store = done()
    ids = store.save_list(["Bills", "Travel"])
    await make(gmail, store).run()
    bills = store.managed[category(store, ids["Bills"])].label_id
    other = store.managed[OTHER].label_id
    for labels in ((bills,), (bills,), (other,)):
        gmail.add_mail(labels=labels, subject="very private subject")
    gmail.calls.clear()

    await make(gmail, store).run()

    assert store.counts == {ids["Bills"]: 2, ids["Travel"]: 0, OTHER_ID: 1}
    assert "messages.get" not in gmail.calls  # no mail is read for a count
    assert sorted(store.label_names) == ["Archive", "Bills", "Other", "Travel"]


async def test_given_a_label_that_is_not_managed_when_synced_then_it_is_left_alone_and_not_listed_or_counted() -> None:
    gmail = FakeGmail()
    store = done()
    store.save_list(["Bills"])
    folder = gmail.add_label("Work")
    mail = gmail.add_mail(labels=(folder,))

    await make(gmail, store).run()

    assert gmail.label_table[folder] == "Work"
    assert gmail.mail_table[mail].labels == {folder}
    assert "Work" not in store.label_names


async def test_given_a_crash_before_the_cursor_when_the_run_repeats_then_nothing_is_done_twice() -> None:
    gmail = FakeGmail()
    store = done()
    ids = store.save_list(["Bills"])
    await make(gmail, store).run()
    store.save_list(["Invoices"], keep={"Invoices": ids["Bills"]})
    store.crash_before_cursor = True

    with pytest.raises(ConnectionResetError):
        await make(gmail, store).run()
    gmail.calls.clear()
    await make(gmail, store).run()

    assert writes(gmail) == []
    assert gmail.label_names().count("Invoices") == 1
    assert store.cursor_version == 2


async def test_given_a_rename_done_in_gmail_but_not_remembered_when_it_repeats_then_it_is_not_renamed_again() -> None:
    gmail = FakeGmail()
    store = done()
    ids = store.save_list(["Bills"])
    await make(gmail, store).run()
    label = store.managed[category(store, ids["Bills"])].label_id
    store.save_list(["Invoices"], keep={"Invoices": ids["Bills"]})
    gmail.label_table[label] = "Invoices"  # Gmail did it; the database still says Bills
    gmail.calls.clear()

    await make(gmail, store).run()

    assert "labels.patch" not in gmail.calls
    assert store.managed[category(store, ids["Bills"])].label_name == "Invoices"


async def test_given_gmail_refuses_one_name_when_synced_then_the_others_are_made_and_the_run_is_not_done(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    gmail = FakeGmail()
    gmail.refuse_name("Bad")
    store = done()
    ids = store.save_list(["Bills", "Bad", "Travel"])

    result = await make(gmail, store).run()

    assert {"Bills", "Travel", "Other", "Archive"} <= set(gmail.label_names())
    assert category(store, ids["Bad"]) not in store.managed
    assert (result.failed, store.cursor_version) == (1, 0)
    assert "Bad" not in caplog.text
    assert "Invalid label name" not in caplog.text


async def test_given_gmail_refuses_the_new_name_of_a_rename_when_synced_then_the_label_keeps_its_name() -> None:
    gmail = FakeGmail()
    store = done()
    ids = store.save_list(["Bills"])
    await make(gmail, store).run()
    label = store.managed[category(store, ids["Bills"])].label_id
    gmail.refuse_name("Bad")
    store.save_list(["Bad"], keep={"Bad": ids["Bills"]})

    result = await make(gmail, store).run()

    assert gmail.label_table[label] == "Bills"
    assert result.failed == 1


@pytest.mark.parametrize("archive", ["INBOX", "Old∕Mail", "Bills"])  # noqa: RUF001  # a look-alike of the slash
async def test_given_an_archive_name_the_policy_refuses_when_synced_then_no_archive_label_is_made(archive: str) -> None:
    gmail = FakeGmail()
    store = done()
    store.save_list(["Bills"])
    store.settings = LabelSettings(other="Other", archive=archive)

    result = await make(gmail, store).run()

    assert ARCHIVE not in store.managed
    assert gmail.label_names().count("Bills") == 1
    assert "Old∕Mail" not in gmail.label_names()  # noqa: RUF001
    assert result.failed == 0


@pytest.mark.parametrize("status", [403, 429])
async def test_given_gmail_fails_in_another_way_when_a_label_is_made_then_the_error_is_not_swallowed(
    status: int,
) -> None:
    gmail = FakeGmail()
    gmail.refuse_name("Archive", status=status)

    with pytest.raises(GmailLabelError):
        await make(gmail, done()).run()


async def test_given_the_sync_runs_when_it_starts_then_the_adapter_and_followers_get_the_managed_set() -> None:
    gmail = FakeGmail()
    store = done()
    store.save_list(["Bills"])
    seen: list[ManagedSet] = []

    class Follower:
        def set_managed(self, managed: ManagedSet) -> None:
            seen.append(managed)

    sync = ListSync(GmailResort(gmail, ManagedSet(()), sleep=lambda _s: None), store, followers=(Follower(),))

    await sync.run()

    assert len(seen) >= 1
    bills = store.managed[category(store, store.categories[0].id)]
    assert any(label.label_id == bills.label_id for label in seen[-1].labels())


@pytest.mark.parametrize("state", [MigrationState.PENDING, MigrationState.CONFIRMED, MigrationState.DONE])
async def test_given_a_state_when_synced_then_the_adapters_get_a_set_that_carries_the_hold(
    state: MigrationState,
) -> None:
    seen: list[bool] = []

    class Sink:
        def set_managed(self, managed: ManagedSet) -> None:
            seen.append(managed.writes_held)

    gmail = FakeGmail()
    sync = ListSync(GmailResort(gmail, ManagedSet(()), sleep=lambda _s: None), FakeListStore(migration=state), [Sink()])

    await sync.run()

    assert seen
    assert set(seen) == {state is not MigrationState.DONE}  # every set it hands out, also after a label was made
