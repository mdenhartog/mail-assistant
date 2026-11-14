"""U-mail-categories-01 criteria 1 to 3: the FakeGmail state machine and its fault hooks (AC-25, AC-51, AC-52)."""

from __future__ import annotations

import pytest
from googleapiclient.errors import HttpError

from tests.fakes.fake_gmail import FakeGmail


def labels_of(gmail: FakeGmail, mid: str) -> set[str]:
    return set(gmail.users().messages().get(userId="me", id=mid).execute()["labelIds"])


def modify(gmail: FakeGmail, mid: str, add: list[str] | None = None, remove: list[str] | None = None) -> dict:
    body = {"addLabelIds": add or [], "removeLabelIds": remove or []}
    return gmail.users().messages().modify(userId="me", id=mid, body=body).execute()


def status(error: HttpError) -> int:
    return int(error.resp.status)


def test_given_an_inbox_mail_when_filed_under_archive_then_it_leaves_the_inbox_and_keeps_the_label() -> None:
    gmail = FakeGmail()
    archive = gmail.add_label("Archive")
    mid = gmail.add_mail()

    modify(gmail, mid, add=[archive], remove=["INBOX"])

    assert labels_of(gmail, mid) == {archive}


def test_given_two_assistant_labels_when_both_are_added_then_the_mail_carries_both() -> None:
    gmail = FakeGmail()
    one, two = gmail.add_label("Assistant/Bills"), gmail.add_label("Assistant/Travel")
    mid = gmail.add_mail()

    modify(gmail, mid, add=[one, two])

    assert {one, two} <= labels_of(gmail, mid)
    assert gmail.assistant_label_count(mid) == 2


def test_given_spam_when_it_is_moved_to_the_inbox_then_spam_goes_and_the_reverse_too() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail(labels=("SPAM",))

    modify(gmail, mid, add=["INBOX"])
    assert labels_of(gmail, mid) == {"INBOX"}

    modify(gmail, mid, add=["TRASH"])
    assert labels_of(gmail, mid) == {"TRASH"}


def test_given_a_deleted_mail_when_it_is_read_or_changed_then_gmail_answers_404() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail()
    gmail.delete_mail(mid)

    with pytest.raises(HttpError) as read:
        labels_of(gmail, mid)
    with pytest.raises(HttpError) as change:
        modify(gmail, mid, remove=["INBOX"])

    assert (status(read.value), status(change.value)) == (404, 404)


def test_given_a_deleted_label_when_it_is_used_then_400_and_mails_lose_it() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    mid = gmail.add_mail(labels=("INBOX", label))

    gmail.delete_label(label)

    assert labels_of(gmail, mid) == {"INBOX"}
    with pytest.raises(HttpError) as error:
        modify(gmail, mid, add=[label])
    assert status(error.value) == 400


def test_given_labels_when_created_renamed_and_deleted_then_the_listing_follows() -> None:
    gmail = FakeGmail()
    labels = gmail.users().labels()

    made = labels.create(userId="me", body={"name": "Assistant/Bills"}).execute()
    labels.patch(userId="me", id=made["id"], body={"name": "Assistant/Invoices"}).execute()

    names = {item["name"] for item in labels.list(userId="me").execute()["labels"]}
    assert "Assistant/Invoices" in names
    assert "Assistant/Bills" not in names
    assert {"INBOX", "SPAM", "TRASH"} <= names


def test_given_a_name_in_use_when_it_is_created_or_renamed_to_then_409_ignoring_case() -> None:
    gmail = FakeGmail()
    gmail.add_label("Archive")
    other = gmail.add_label("Assistant/Bills")
    labels = gmail.users().labels()

    with pytest.raises(HttpError) as created:
        labels.create(userId="me", body={"name": "archive"}).execute()
    with pytest.raises(HttpError) as renamed:
        labels.patch(userId="me", id=other, body={"name": "ARCHIVE"}).execute()

    assert (status(created.value), status(renamed.value)) == (409, 409)


def test_given_an_authentication_results_header_when_the_mail_is_read_then_it_is_in_the_headers() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail(auth_results="mx.example; dmarc=pass header.from=accounts.example")

    payload = gmail.users().messages().get(userId="me", id=mid, format="full").execute()["payload"]

    names = {h["name"]: h["value"] for h in payload["headers"]}
    assert names["Authentication-Results"].startswith("mx.example; dmarc=pass")


def test_given_fail_after_change_when_a_label_is_changed_then_the_change_stays_and_the_call_raises() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    mid = gmail.add_mail()
    gmail.fail_after_next_change()

    with pytest.raises(ConnectionResetError):
        modify(gmail, mid, add=[label], remove=["INBOX"])

    assert labels_of(gmail, mid) == {label}  # a retry sees the mail already moved
    assert modify(gmail, mid, add=[label], remove=["INBOX"])["labelIds"] == [label]  # the hook fires once


@pytest.mark.parametrize("code", [429, 500, 503])
def test_given_a_transient_fault_when_the_next_call_runs_then_it_fails_without_changing_anything(code: int) -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail()
    gmail.fail_next(code, times=2)

    for _ in range(2):
        with pytest.raises(HttpError) as error:
            modify(gmail, mid, remove=["INBOX"])
        assert status(error.value) == code

    assert labels_of(gmail, mid) == {"INBOX"}
    modify(gmail, mid, remove=["INBOX"])
    assert labels_of(gmail, mid) == set()


def test_given_two_overlapping_creates_when_both_run_then_the_second_gets_already_exists() -> None:
    gmail = FakeGmail()
    labels = gmail.users().labels()
    gmail.race_on_create("Archive")  # another run creates it between this run's list and create

    assert [item["name"] for item in labels.list(userId="me").execute()["labels"]].count("Archive") == 0
    with pytest.raises(HttpError) as second:
        labels.create(userId="me", body={"name": "Archive"}).execute()

    assert status(second.value) == 409
    assert "exists" in str(second.value).lower()
    assert gmail.label_names().count("Archive") == 1


def test_given_a_change_mid_apply_when_the_caller_modifies_then_the_user_change_lands_first() -> None:
    gmail = FakeGmail()
    one, two = gmail.add_label("Assistant/Bills"), gmail.add_label("Assistant/Travel")
    mid = gmail.add_mail(labels=("INBOX", one))
    gmail.change_before_next_modify(mid, add=[two])

    result = modify(gmail, mid, remove=["INBOX"])

    assert set(result["labelIds"]) == {one, two}
    assert gmail.assistant_label_count(mid) == 2
