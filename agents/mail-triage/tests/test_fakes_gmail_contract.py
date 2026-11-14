"""U-mail-categories-01 criterion 4: the FakeGmail answers like the real Gmail wrapper expects.

The real ``GmailReader`` (list, read, add, remove, create) runs on the FakeGmail as its service, and the same
operations run on the raw resource chain next to a fixture of Gmail's documented response shapes. The wrapper has no
rename (the label sync of a later unit adds one), so rename is checked on the raw chain only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from googleapiclient.errors import HttpError

from app.adapters.gmail_read import GmailReader
from tests.fakes.fake_gmail import FakeGmail

# Shapes documented for the Gmail v1 API (users.labels, users.messages); the fake must return at least these keys.
LABEL_KEYS = {"id", "name"}
MODIFY_KEYS = {"id", "threadId", "labelIds"}


def reader(gmail: FakeGmail) -> GmailReader:
    return GmailReader(gmail, sleep=lambda _seconds: None)


def test_given_unread_inbox_mail_when_listed_by_the_real_wrapper_then_the_fake_returns_the_same_ids() -> None:
    gmail = FakeGmail()
    one = gmail.add_mail(labels=("INBOX", "UNREAD"))
    two = gmail.add_mail(labels=("INBOX", "UNREAD"))
    gmail.add_mail(labels=("INBOX",))  # read
    gmail.add_mail(labels=("SPAM", "UNREAD"))

    ids = reader(gmail).list_unread_before(datetime(2030, 1, 1, tzinfo=UTC))

    assert ids == [two, one]  # newest first, like Gmail


def test_given_a_mail_when_read_by_the_real_wrapper_then_headers_text_and_labels_come_through() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail(
        sender="Name <a@example.test>", subject="hello", text="body text", auth_results="mx; dmarc=pass"
    )

    mail = reader(gmail).fetch(mid)

    assert (mail.sender, mail.subject, mail.text) == ("a@example.test", "hello", "body text")
    assert mail.headers["Authentication-Results"] == "mx; dmarc=pass"
    assert mail.labels == frozenset({"INBOX"})


def test_given_a_missing_label_when_the_real_wrapper_ensures_it_then_it_is_created_once_and_reused() -> None:
    gmail = FakeGmail()

    first = reader(gmail).ensure_label("Assistant/Bills")
    second = reader(gmail).ensure_label("Assistant/Bills")

    assert first == second
    assert gmail.label_names().count("Assistant/Bills") == 1


def test_given_a_mail_when_the_real_wrapper_files_it_then_label_is_added_and_inbox_removed() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail()
    label = reader(gmail).ensure_label("Assistant/Bills")

    reader(gmail).file(mid, label)

    assert reader(gmail).fetch(mid).labels == frozenset({label})


def test_given_the_raw_chain_when_labels_are_created_renamed_listed_then_the_documented_keys_are_present() -> None:
    gmail = FakeGmail()
    labels = gmail.users().labels()

    made = labels.create(userId="me", body={"name": "Assistant/Bills"}).execute()
    renamed = labels.patch(userId="me", id=made["id"], body={"name": "Assistant/Invoices"}).execute()
    listed = labels.list(userId="me").execute()["labels"]

    assert set(made) >= LABEL_KEYS
    assert set(renamed) >= LABEL_KEYS
    assert all(set(item) >= LABEL_KEYS for item in listed)
    assert renamed["id"] == made["id"]


def test_given_the_raw_chain_when_a_mail_is_modified_then_the_documented_keys_are_present() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail()

    result: dict[str, Any] = (
        gmail.users().messages().modify(userId="me", id=mid, body={"removeLabelIds": ["INBOX"]}).execute()
    )

    assert set(result) >= MODIFY_KEYS


@pytest.mark.parametrize("code", [429, 503])
def test_given_a_transient_fault_when_the_real_wrapper_retries_then_it_succeeds_after_backing_off(code: int) -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail()
    gmail.fail_next(code, times=2)
    sleeps: list[float] = []

    mail = GmailReader(gmail, sleep=sleeps.append).fetch(mid)

    assert mail.message_id == mid
    assert len(sleeps) == 2


def test_given_a_deleted_mail_when_the_real_wrapper_reads_it_then_the_404_surfaces() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail()
    gmail.delete_mail(mid)

    with pytest.raises(HttpError) as error:
        reader(gmail).fetch(mid)

    assert error.value.resp.status == 404
