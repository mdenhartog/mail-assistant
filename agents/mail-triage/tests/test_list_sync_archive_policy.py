"""REV-003: the list sync checks the archive label name with the shared policy and the current categories (ADR-0059)."""
# ruff: noqa: RUF001  # the look-alike characters are the subject of these tests

from __future__ import annotations

from app.adapters.gmail_resort import GmailResort
from app.core.scope import ArchiveLabel
from app.usecases.list_sync import ArchiveNames, ListSync
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.list_store import FakeListStore


def _sync(gmail: FakeGmail, store: FakeListStore, ref: ArchiveLabel) -> ListSync:
    return ListSync(GmailResort(gmail, ref, sleep=lambda _s: None), store, ref)


async def test_given_the_archive_name_is_a_category_label_when_the_sync_runs_then_it_is_not_made_as_the_archive() -> (
    None
):
    gmail = FakeGmail()
    store = FakeListStore()
    store.save_list(["Archive"])  # its label is Assistant/Archive, the default archive name
    store.archive = ArchiveNames(wanted="Assistant/Archive", applied=None)
    ref = ArchiveLabel("Assistant/Archive")

    await _sync(gmail, store, ref).run()

    assert ref.label_id is None  # the label that exists is the category's, never the protected archive label
    assert gmail.label_names().count("Assistant/Archive") == 1


async def test_given_a_look_alike_archive_name_when_the_sync_runs_then_no_label_is_made() -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    store.archive = ArchiveNames(wanted="Old∕Mail", applied=None)
    ref = ArchiveLabel("Old∕Mail")

    await _sync(gmail, store, ref).run()

    assert "Old∕Mail" not in gmail.label_names()
    assert ref.label_id is None
