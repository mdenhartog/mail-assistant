"""U-mail-categories-38: a label name that Gmail refuses must not stop the sync of the other labels (AC-25, AC-40).

The first deploy against a real mailbox showed the sync failing with HTTP 400 ``invalidArgument`` before it seeded
anything. A refused name is a problem of that one label: the others are still made, and the run says it did not finish.
"""

from __future__ import annotations

import logging

import pytest
from googleapiclient.errors import HttpError

from app.adapters.gmail_resort import GmailResort
from app.usecases.list_sync import ListSync
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.list_store import FakeListStore


def make(gmail: FakeGmail, store: FakeListStore) -> ListSync:
    return ListSync(GmailResort(gmail, sleep=lambda _s: None), store)


async def test_given_gmail_refuses_the_archive_label_when_the_sync_runs_then_the_categories_are_made_and_it_finishes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    gmail = FakeGmail()
    gmail.refuse_name("Archive")
    store = FakeListStore()
    store.save_list(["Bills"])

    result = await make(gmail, store).run()

    assert "Assistant/Bills" in gmail.label_names()
    assert "Assistant/Other" in gmail.label_names()
    assert "Archive" not in gmail.label_names()
    assert (result.failed, store.cursor_version, store.version) == (0, 1, 1)  # Archive is optional: the run is done
    assert "refused" in caplog.text
    assert "Invalid label name" not in caplog.text


async def test_given_gmail_refuses_the_archive_label_on_a_first_start_when_the_sync_runs_then_the_list_is_seeded() -> (
    None
):
    gmail = FakeGmail()
    gmail.refuse_name("Archive")
    gmail.add_label("Assistant/Travel")
    store = FakeListStore()

    await make(gmail, store).run()

    assert store.seeded == [("Travel",)]


async def test_given_gmail_refuses_one_category_label_when_the_sync_runs_then_the_others_are_made_and_it_is_not_done(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    gmail = FakeGmail()
    gmail.refuse_name("Assistant/Bad")
    store = FakeListStore()
    ids = store.save_list(["Bills", "Bad", "Travel"])

    result = await make(gmail, store).run()

    assert {"Assistant/Bills", "Assistant/Travel", "Assistant/Other"} <= set(gmail.label_names())
    assert "Assistant/Bad" not in gmail.label_names()
    assert ids["Bad"] not in store.labels  # no label to remember for it
    assert result.failed == 1
    assert store.cursor_version == 0  # the cursor moves only when nothing failed (the run repeats)
    assert "Bad" not in caplog.text


async def test_given_gmail_refuses_the_new_name_of_a_rename_when_the_sync_runs_then_the_label_keeps_its_name() -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    ids = store.save_list(["Bills"])
    await make(gmail, store).run()
    label = store.labels[ids["Bills"]].label_id
    gmail.refuse_name("Assistant/Bad")
    store.save_list(["Bad"], keep={"Bad": ids["Bills"]})

    result = await make(gmail, store).run()

    assert gmail.label_table[label] == "Assistant/Bills"
    assert result.failed == 1


@pytest.mark.parametrize("status", [403, 429])
async def test_given_gmail_fails_in_another_way_when_the_archive_is_made_then_the_error_is_not_swallowed(
    status: int,
) -> None:
    gmail = FakeGmail()
    gmail.refuse_name("Archive", status=status)

    with pytest.raises(HttpError):
        await make(gmail, FakeListStore()).run()
