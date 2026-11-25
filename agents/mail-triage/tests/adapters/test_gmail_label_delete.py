"""U-label-prefix-removal-07, criteria 1 to 7 (ADR-0060 point 5, AC 7, 8, 10b, 21, 22, 30): the Gmail label delete.

The adapter deletes one label by id, only after it re-read the label and every check holds. Anything unclear keeps
the label. The errors carry codes and never a label name.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest

from app.adapters.gmail_label_delete import GmailLabelDelete, LabelDeleteRefused, LabelState
from app.adapters.gmail_read import GmailLabelError
from tests.fakes.fake_gmail import FakeGmail

if TYPE_CHECKING:
    from collections.abc import Callable

PROBE_NAME = "Secret-Name-4711"


def adapter(gmail: FakeGmail) -> GmailLabelDelete:
    return GmailLabelDelete(gmail, sleep=lambda _seconds: None)


class _Answer:
    def __init__(self, value: Any) -> None:
        self._value = value

    def execute(self) -> Any:
        return self._value


class Garbling(FakeGmail):
    """A mailbox whose answer to one call is rewritten, to model an unclear answer from Gmail."""

    def __init__(self) -> None:
        super().__init__()
        self.garble: dict[str, Callable[[Any], Any]] = {}

    def request(self, name: str, action: Any) -> Any:
        inner = super().request(name, action)
        rewrite = self.garble.get(name)
        return _Answer(rewrite(inner.execute())) if rewrite else inner


def refusal(gmail: FakeGmail, label_id: str) -> str:
    with pytest.raises(LabelDeleteRefused) as raised:
        adapter(gmail).delete(label_id)
    assert "labels.delete" not in gmail.calls  # Gmail was not asked to delete
    return str(raised.value)


# --- criterion 1 -------------------------------------------------------------------------------------------------


def test_given_an_empty_user_label_when_deleted_then_gmail_gets_one_delete_by_that_id() -> None:
    gmail = FakeGmail()
    empty = gmail.add_label("Bills")
    other = gmail.add_label("Taxes")

    adapter(gmail).delete(empty)

    assert gmail.calls.count("labels.delete") == 1
    assert empty not in gmail.label_table
    assert other in gmail.label_table


def test_given_a_label_when_read_then_type_counts_and_children_come_back() -> None:
    gmail = FakeGmail()
    parent = gmail.add_label("Bills")
    gmail.add_label("Bills/2026")
    gmail.add_label("Billsx")  # starts with the name but is no child
    gmail.add_mail(labels=("INBOX", parent))

    state = adapter(gmail).read_label(parent)

    assert state == LabelState(parent, "Bills", "user", messages_total=1, threads_total=1, has_children=True)
    assert adapter(gmail).read_label(gmail.label_id("Billsx")).has_children is False


def test_given_a_parent_in_other_case_when_read_then_a_child_is_still_found() -> None:
    gmail = FakeGmail()
    parent = gmail.add_label("bills")
    gmail.add_label("BILLS/Old")

    assert adapter(gmail).read_label(parent).has_children is True


def test_given_two_filters_when_read_then_every_added_label_id_is_returned() -> None:
    gmail = FakeGmail()
    gmail.add_filter(add_label_ids=["Label_1", "Label_2"])
    gmail.add_filter(add_label_ids=["Label_3"])

    assert adapter(gmail).labels_in_filters() == {"Label_1", "Label_2", "Label_3"}
    assert adapter(FakeGmail()).labels_in_filters() == frozenset()


def test_given_trash_mail_when_checked_then_the_list_call_includes_spam_and_trash_and_asks_for_one() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    seen: dict[str, Any] = {}
    original = gmail.messages

    class Spy:
        def list(self, **kw: Any) -> Any:
            seen.update(kw)
            return original().list(**kw)

    gmail.messages = Spy  # type: ignore[method-assign,assignment]
    gmail.add_mail(labels=("TRASH", bills))

    assert adapter(gmail).has_mail_including_trash(bills) is True
    assert (seen["labelIds"], seen["includeSpamTrash"], seen["maxResults"]) == ([bills], True, 1)


# --- criteria 2 to 5 ---------------------------------------------------------------------------------------------


def test_given_a_label_with_one_mail_when_deleted_then_it_is_refused_and_gmail_is_not_called_to_delete() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.add_mail(labels=("INBOX", bills))

    assert refusal(gmail, bills) == "label_has_mail"
    assert bills in gmail.label_table


def test_given_a_label_with_only_trash_or_spam_mail_when_deleted_then_it_is_refused() -> None:
    for folder in ("TRASH", "SPAM"):
        gmail = FakeGmail()
        bills = gmail.add_label("Bills")
        gmail.add_mail(labels=(folder, bills))

        assert adapter(gmail).read_label(bills).messages_total == 0  # the counters do not show it
        assert refusal(gmail, bills) == "label_has_mail_listed"
        assert bills in gmail.label_table


@pytest.mark.parametrize("label_id", ["INBOX", "SENT", "SPAM", "TRASH", "UNREAD", "CATEGORY_PERSONAL"])
def test_given_a_system_label_when_deleted_then_it_is_refused_even_if_empty(label_id: str) -> None:
    gmail = FakeGmail()
    gmail.add_system_label("CATEGORY_PERSONAL")

    assert refusal(gmail, label_id) == "label_not_user_type"
    assert label_id in gmail.label_table


@pytest.mark.parametrize("name", ["STARRED", "important", "Chat", "draft", "CATEGORY_UPDATES", "category_forums"])
def test_given_a_user_label_with_a_system_name_when_deleted_then_it_is_refused_by_name(name: str) -> None:
    gmail = FakeGmail()
    label = gmail.add_label(name)  # the fake gives it type user: the name guard is the second line

    assert refusal(gmail, label) == "label_is_system_name"


@pytest.mark.parametrize("label_id", ["INBOX", "STARRED", "CATEGORY_SOCIAL", "CHAT"])
def test_given_a_system_id_reported_as_user_type_when_deleted_then_it_is_refused_by_id(label_id: str) -> None:
    gmail = Garbling()
    if label_id not in gmail.label_table:
        gmail.add_system_label(label_id)
    gmail.garble["labels.get"] = lambda answer: {**answer, "type": "user"}

    assert refusal(gmail, label_id) == "label_is_system_id"


def test_given_a_label_that_a_filter_adds_when_deleted_then_it_is_refused() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.add_filter(add_label_ids=[bills])

    assert refusal(gmail, bills) == "label_in_filter"
    assert bills in gmail.label_table


def test_given_a_label_with_a_child_when_deleted_then_it_is_refused() -> None:
    gmail = FakeGmail()
    parent = gmail.add_label("Bills")
    gmail.add_label("Bills/2026")

    assert refusal(gmail, parent) == "label_has_child"


def test_given_an_unknown_id_when_deleted_then_it_is_refused() -> None:
    gmail = FakeGmail()

    assert refusal(gmail, "Label_404") == "label_unknown"


# --- criterion 6 -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("call", ["labels.list", "labels.get", "settings.filters.list", "messages.list"])
@pytest.mark.parametrize("status", [403, 429, 500])
def test_given_any_gmail_error_when_deleted_then_the_label_is_kept_and_the_error_has_no_name(
    call: str, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    gmail = FakeGmail()
    secret = gmail.add_label(PROBE_NAME)
    gmail.fail_call(call, status, times=5)  # more than the retries the adapter makes
    caplog.set_level(logging.DEBUG)

    code = refusal(gmail, secret)

    assert code == "label_check_failed"
    assert secret in gmail.label_table
    assert PROBE_NAME not in code + caplog.text


UNCLEAR: list[tuple[str, Callable[[Any], Any]]] = [
    ("labels.get", lambda answer: {"id": answer["id"]}),
    ("labels.get", lambda answer: {**answer, "messagesTotal": "0"}),
    ("labels.get", lambda answer: {**answer, "threadsTotal": None}),
    ("labels.get", lambda answer: {**answer, "messagesTotal": -1}),
    ("labels.get", lambda _answer: "garbage"),
    ("labels.list", lambda _answer: {"labels": "garbage"}),
    ("labels.list", lambda _answer: {}),
    ("settings.filters.list", lambda _answer: {"filter": "garbage"}),
    ("settings.filters.list", lambda _answer: {"filter": [{"action": "garbage"}]}),
    ("settings.filters.list", lambda _answer: "garbage"),
    ("messages.list", lambda _answer: "garbage"),
    ("messages.list", lambda _answer: {"messages": "garbage"}),
]


@pytest.mark.parametrize(("call", "garble"), UNCLEAR)
def test_given_an_unclear_answer_when_deleted_then_the_label_counts_as_not_empty_and_is_kept(
    call: str, garble: Callable[[Any], Any]
) -> None:
    gmail = Garbling()
    bills = gmail.add_label("Bills")
    gmail.garble[call] = garble

    assert refusal(gmail, bills) in {"label_check_failed", "label_unknown", "label_has_mail_listed"}
    assert bills in gmail.label_table


def test_given_the_delete_call_fails_when_deleted_then_the_error_has_status_and_reason_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gmail = FakeGmail()
    secret = gmail.add_label(PROBE_NAME)
    gmail.fail_call("labels.delete", 403, times=1)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(GmailLabelError) as raised:
        adapter(gmail).delete(secret)

    assert str(raised.value) == "gmail_label_call_failed status=403 reason=forbidden"
    assert secret in gmail.label_table
    assert PROBE_NAME not in caplog.text


def test_given_the_delete_call_answers_not_found_when_deleted_then_it_counts_as_deleted_without_a_name_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gmail = FakeGmail()
    gone = gmail.add_label(PROBE_NAME)
    gmail.fail_call("labels.delete", 404, times=1)  # deleted by hand between the checks and the call
    caplog.set_level(logging.DEBUG)

    adapter(gmail).delete(gone)  # no error: the label is gone, which is what was wanted

    assert gmail.calls.count("labels.delete") == 1
    assert PROBE_NAME not in caplog.text


def test_given_refusals_when_logged_then_no_label_name_is_in_the_log(caplog: pytest.LogCaptureFixture) -> None:
    gmail = FakeGmail()
    bills = gmail.add_label(PROBE_NAME)
    gmail.add_mail(labels=("INBOX", bills))
    caplog.set_level(logging.DEBUG)

    refusal(gmail, bills)

    assert PROBE_NAME not in caplog.text
    assert "label_has_mail" in caplog.text


# --- criterion 7 -------------------------------------------------------------------------------------------------


def test_given_a_mail_injected_before_the_delete_when_deleted_then_the_re_read_and_delete_are_adjacent() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.inject_mail_before_next("labels.delete", labels=("INBOX", bills))

    adapter(gmail).delete(bills)

    # The window is the single gap between the final re-read and the delete: nothing else is called in between.
    assert gmail.calls[-2:] == ["labels.get", "labels.delete"]
    # The recorded outcome (accepted risk A2): the label is gone, the mail is still in the mailbox, only unlabelled.
    assert bills not in gmail.label_table
    assert [mail.labels for mail in gmail.mail_table.values()] == [{"INBOX"}]


def test_given_a_mail_injected_before_the_final_re_read_when_deleted_then_the_label_is_kept() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.inject_mail_before_next("labels.get", labels=("INBOX", bills), skip=1)  # the second read is the final one

    assert refusal(gmail, bills) == "label_has_mail"


def test_given_the_checks_when_run_then_the_final_re_read_comes_after_every_other_check() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")

    adapter(gmail).delete(bills)

    assert gmail.calls == [
        "labels.list",
        "labels.get",
        "settings.filters.list",
        "messages.list",
        "labels.list",
        "labels.get",
        "labels.delete",
    ]
