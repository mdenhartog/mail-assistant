"""U-label-prefix-removal-07 criterion 8: what the FakeGmail models for the label delete (counts, type, filters ...)."""

from __future__ import annotations

from typing import Any

import pytest
from googleapiclient.errors import HttpError

from tests.fakes import fake_gmail
from tests.fakes.fake_gmail import FakeGmail


def get(gmail: FakeGmail, label_id: str) -> dict[str, Any]:
    return gmail.users().labels().get(userId="me", id=label_id).execute()  # type: ignore[no-any-return]


def listing(gmail: FakeGmail, **kw: Any) -> dict[str, Any]:
    return gmail.users().messages().list(userId="me", **kw).execute()  # type: ignore[no-any-return]


def test_given_labelled_mail_when_the_label_is_read_then_it_has_a_type_and_message_and_thread_counts() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.add_mail(labels=("INBOX", bills))
    gmail.add_mail(labels=("INBOX", bills), thread="shared")
    gmail.add_mail(labels=("INBOX", bills), thread="shared")

    label = get(gmail, bills)

    assert (label["type"], label["messagesTotal"], label["threadsTotal"]) == ("user", 3, 2)
    assert get(gmail, "INBOX")["type"] == "system"


def test_given_trash_mail_when_the_label_is_read_then_the_counts_are_zero_but_the_spam_trash_list_finds_it() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.add_mail(labels=("TRASH", bills))

    label = get(gmail, bills)

    assert (label["messagesTotal"], label["threadsTotal"]) == (0, 0)  # the lag the real check must not trust
    assert listing(gmail, labelIds=[bills], maxResults=1) == {}
    assert listing(gmail, labelIds=[bills], includeSpamTrash=True, maxResults=1)["messages"]


def test_given_system_and_nested_labels_when_listed_then_the_type_shows_and_nested_names_are_plain_names() -> None:
    gmail = FakeGmail()
    parent = gmail.add_label("Bills")
    child = gmail.add_label("Bills/2026")
    category = gmail.add_system_label("CATEGORY_PERSONAL")

    entries = {e["id"]: e for e in gmail.users().labels().list(userId="me").execute()["labels"]}

    assert entries[parent]["type"] == entries[child]["type"] == "user"
    assert entries[category]["type"] == "system"
    assert entries[child]["name"] == "Bills/2026"


def test_given_a_name_in_other_case_when_created_then_gmail_answers_409_with_the_reason() -> None:
    gmail = FakeGmail()
    gmail.add_label("Bills")

    with pytest.raises(HttpError) as raised:
        gmail.users().labels().create(userId="me", body={"name": "BILLS"}).execute()

    assert raised.value.resp.status == 409


@pytest.mark.parametrize("status", [403, 429])
def test_given_an_injected_status_when_the_next_call_runs_then_it_fails_with_that_status_and_changes_nothing(
    status: int,
) -> None:
    gmail = FakeGmail()
    gmail.add_label("Bills")
    gmail.fail_next(status)

    with pytest.raises(HttpError) as raised:
        gmail.users().labels().list(userId="me").execute()

    assert raised.value.resp.status == status
    assert "Bills" in gmail.label_names()


def test_given_filters_when_listed_then_every_add_label_id_shows_and_no_filter_gives_an_empty_answer() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    assert gmail.users().settings().filters().list(userId="me").execute() == {}

    gmail.add_filter(add_label_ids=[bills, "STARRED"])

    answer = gmail.users().settings().filters().list(userId="me").execute()
    assert answer["filter"][0]["action"]["addLabelIds"] == [bills, "STARRED"]
    assert gmail.calls[-1] == "settings.filters.list"


def test_given_a_hook_when_the_next_call_of_that_name_runs_then_the_mail_arrives_just_before_it() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.inject_mail_before_next("labels.delete", labels=("INBOX", bills))

    assert get(gmail, bills)["messagesTotal"] == 0
    gmail.users().labels().delete(userId="me", id=bills).execute()

    assert len(gmail.mail_table) == 1  # the mail stayed in the mailbox
    assert bills not in gmail.label_table
    assert all(bills not in mail.labels for mail in gmail.mail_table.values())
    assert gmail.calls[-2:] == ["labels.get", "labels.delete"]


def test_given_a_system_label_or_an_unknown_id_when_deleted_then_gmail_refuses() -> None:
    gmail = FakeGmail()
    statuses = []
    for label_id in ("INBOX", "Label_99"):
        with pytest.raises(HttpError) as raised:
            gmail.users().labels().delete(userId="me", id=label_id).execute()
        statuses.append(raised.value.resp.status)

    assert statuses == [400, 404]


def test_given_the_fake_when_inspected_then_it_has_no_assistant_prefix_and_no_assistant_query_matcher() -> None:
    gmail = FakeGmail()
    mail = gmail.add_mail(labels=("SENT",))

    assert not hasattr(fake_gmail, "ASSISTANT_PREFIX")
    assert not hasattr(gmail, "assistant_label_count")
    assert not hasattr(gmail, "matches_query")
    assert listing(gmail, q="label:assistant")["messages"][0]["id"] == mail  # a query is not modelled: all mail


def test_given_a_named_failure_when_that_call_runs_then_only_that_call_fails_the_given_number_of_times() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.fail_call("labels.get", 429, times=2)

    gmail.users().labels().list(userId="me").execute()  # other calls are not touched
    for _ in range(2):
        with pytest.raises(HttpError) as raised:
            get(gmail, bills)
        assert raised.value.resp.status == 429
    assert get(gmail, bills)["id"] == bills


def test_given_a_skip_when_a_mail_is_injected_then_it_arrives_before_the_later_call_of_that_name() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.inject_mail_before_next("labels.get", labels=("INBOX", bills), skip=1)

    assert get(gmail, bills)["messagesTotal"] == 0
    assert get(gmail, bills)["messagesTotal"] == 1
