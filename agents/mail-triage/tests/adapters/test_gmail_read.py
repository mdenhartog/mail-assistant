"""U-05: reading and labelling Gmail through a small, fixed set of calls (AC-1, AC-2, AC-12, AC-23, AC-28, AC-29)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httplib2
import pytest
from googleapiclient.errors import HttpError

from app.adapters import gmail_auth, gmail_read
from app.adapters.gmail_read import GmailReader, HistoryExpiredError

SOURCE = Path(gmail_read.__file__).read_text(encoding="utf-8")


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def http_error(status: int, reason: str = "") -> HttpError:
    return HttpError(
        httplib2.Response({"status": status}), b'{"error": {"errors": [{"reason": "%s"}]}}' % reason.encode()
    )


class Request:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes

    def execute(self) -> Any:
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeGmail:
    """Just enough of the Gmail resource chain; it records every call so tests can assert what was (not) used."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.history_pages: list[Any] = []
        self.message_pages: list[Any] = []  # per page: a dict, or a list of outcomes (errors first)
        self.messages: dict[str, Any] = {}
        self.labels: list[dict[str, str]] = []
        self.modify_outcomes: list[Any] = [{}]

    def users(self) -> FakeGmail:
        return self

    def getProfile(self, **kw: Any) -> Request:  # noqa: N802
        self.calls.append(("getProfile", kw))
        return Request([{"historyId": "100"}])

    def history(self) -> FakeGmail:
        return self

    def messages_resource(self) -> FakeGmail:
        return self

    def attachments(self) -> FakeGmail:
        self.calls.append(("attachments", {}))
        return self

    def list(self, **kw: Any) -> Request:
        self.calls.append(("list", kw))
        if "startHistoryId" in kw:
            return Request([self.history_pages[int(kw.get("pageToken") or 0)]])
        if "q" in kw:
            page = self.message_pages[int(kw.get("pageToken") or 0)]
            return Request(page if isinstance(page, list) else [page])
        return Request([{"labels": self.labels}])

    def get(self, **kw: Any) -> Request:
        self.calls.append(("get", kw))
        return Request([self.messages[kw["id"]]])

    def create(self, **kw: Any) -> Request:
        self.calls.append(("create", kw))
        return Request([{"id": "Label_new", "name": kw["body"]["name"]}])

    def modify(self, **kw: Any) -> Request:
        self.calls.append(("modify", kw))
        return Request(self.modify_outcomes)

    def labels_resource(self) -> FakeGmail:
        return self


class Chain:
    """users().history() / users().messages() / users().labels() all return the same recording fake."""

    def __init__(self, fake: FakeGmail) -> None:
        self.fake = fake

    def users(self) -> Chain:
        return self

    def getProfile(self, **kw: Any) -> Request:  # noqa: N802
        return self.fake.getProfile(**kw)

    def history(self) -> FakeGmail:
        return self.fake

    def messages(self) -> FakeGmail:
        return self.fake

    def labels(self) -> FakeGmail:
        return self.fake


@pytest.fixture
def gmail() -> FakeGmail:
    return FakeGmail()


def reader(gmail: FakeGmail, sleeps: list[float] | None = None) -> GmailReader:
    record = sleeps if sleeps is not None else []
    return GmailReader(Chain(gmail), sleep=record.append)  # type: ignore[arg-type]


def message(mid: str, labels: list[str]) -> dict[str, Any]:
    return {"message": {"id": mid, "threadId": f"t-{mid}", "labelIds": labels}}


def test_given_two_pages_of_history_when_listing_new_mail_then_all_inbox_mails_are_returned(gmail: FakeGmail) -> None:
    gmail.history_pages = [
        {"history": [{"messagesAdded": [message("a", ["INBOX"])]}], "nextPageToken": "1", "historyId": "110"},
        {"history": [{"messagesAdded": [message("b", ["INBOX", "UNREAD"])]}], "historyId": "120"},
    ]

    ids, latest = reader(gmail).list_new("100")

    assert ids == ["a", "b"]
    assert latest == "120"


def test_given_the_agents_own_sent_mail_when_listing_then_it_is_excluded(gmail: FakeGmail) -> None:
    gmail.history_pages = [
        {
            "history": [
                {"messagesAdded": [message("mine", ["SENT"]), message("in", ["INBOX"]), message("x", ["DRAFT"])]}
            ],
            "historyId": "130",
        }
    ]

    ids, _ = reader(gmail).list_new("100")

    assert ids == ["in"]


def test_given_no_stored_position_when_listing_then_it_starts_from_now_without_old_mail(gmail: FakeGmail) -> None:
    ids, latest = reader(gmail).list_new(None)

    assert (ids, latest) == ([], "100")


def test_given_a_history_position_that_expired_when_listing_then_the_caller_is_told(gmail: FakeGmail) -> None:
    class Gone(FakeGmail):
        def list(self, **kw: Any) -> Request:
            return Request([http_error(404)])

    with pytest.raises(HistoryExpiredError):
        reader(Gone()).list_new("1")


def test_given_a_mail_with_attachments_when_fetched_then_only_headers_and_text_are_read(gmail: FakeGmail) -> None:
    gmail.messages["m1"] = {
        "id": "m1",
        "threadId": "t1",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "Anna <anna@example.com>"},
                {"name": "Reply-To", "value": "other@example.org"},
                {"name": "Subject", "value": "Dinner?"},
                {"name": "Message-ID", "value": "<abc@example.com>"},
                {"name": "Authentication-Results", "value": "mx; spf=pass dkim=pass dmarc=pass"},
            ],
            "parts": [
                {"mimeType": "text/plain", "filename": "", "body": {"data": b64("Are you free on Friday?")}},
                {"mimeType": "application/pdf", "filename": "menu.pdf", "body": {"attachmentId": "att-1", "size": 9}},
            ],
        },
    }

    mail = reader(gmail).fetch("m1")

    assert mail.text == "Are you free on Friday?"
    assert mail.sender == "anna@example.com"
    assert mail.reply_to == "other@example.org"
    assert mail.subject == "Dinner?"
    assert mail.has_attachment is True
    assert "attachments" not in [name for name, _ in gmail.calls]
    get_call = next(kw for name, kw in gmail.calls if name == "get")
    assert get_call["format"] == "full"
    assert "fields" in get_call


def test_given_a_mail_with_only_html_when_fetched_then_the_text_is_extracted_without_scripts(gmail: FakeGmail) -> None:
    html = "<html><style>p{}</style><script>alert(1)</script><p>Hello <b>Marco</b></p></html>"
    gmail.messages["m2"] = {
        "id": "m2",
        "threadId": "t2",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/html",
            "headers": [{"name": "From", "value": "news@example.com"}, {"name": "Subject", "value": "Hi"}],
            "body": {"data": b64(html)},
        },
    }

    mail = reader(gmail).fetch("m2")

    assert mail.text == "Hello Marco"
    assert mail.has_attachment is False
    assert mail.reply_to is None


def test_given_a_category_label_when_filing_then_exactly_that_label_is_added_and_inbox_removed(
    gmail: FakeGmail,
) -> None:
    reader(gmail).file("m1", "Label_7")

    name, kw = gmail.calls[-1]
    assert name == "modify"
    assert kw["id"] == "m1"
    assert kw["body"] == {"addLabelIds": ["Label_7"], "removeLabelIds": ["INBOX"]}


def test_given_an_existing_label_when_ensured_then_it_is_found_and_a_missing_one_is_created(gmail: FakeGmail) -> None:
    gmail.labels = [{"id": "Label_1", "name": "Assistant/Finance"}]
    gmail_reader = reader(gmail)

    assert gmail_reader.ensure_label("Assistant/Finance") == "Label_1"
    assert gmail_reader.ensure_label("Assistant/Travel") == "Label_new"


@pytest.mark.parametrize("name", ["INBOX", "Work", "Assistant", "../Assistant/x"])
def test_given_a_label_outside_the_prefix_when_ensured_then_it_is_refused(gmail: FakeGmail, name: str) -> None:
    with pytest.raises(ValueError, match="Assistant/"):
        reader(gmail).ensure_label(name)

    assert not [c for c in gmail.calls if c[0] == "create"]


@pytest.mark.parametrize("word", ["trash", "delete", "spam", "batchDelete", "untrash"])
def test_given_the_module_source_when_scanned_then_it_has_no_trash_delete_or_spam_operation(word: str) -> None:
    assert word.lower() not in SOURCE.lower()


def test_given_rate_limiting_when_a_call_runs_then_it_retries_with_backoff_and_then_succeeds(gmail: FakeGmail) -> None:
    gmail.modify_outcomes = [http_error(429), http_error(403, "rateLimitExceeded"), {}]
    sleeps: list[float] = []

    reader(gmail, sleeps).file("m1", "Label_7")

    assert len([c for c in gmail.calls if c[0] == "modify"]) == 1  # one request object, executed three times
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]


def test_given_a_permanent_error_when_a_call_runs_then_it_is_raised_without_retry(gmail: FakeGmail) -> None:
    gmail.modify_outcomes = [http_error(403, "insufficientPermissions")]
    sleeps: list[float] = []

    with pytest.raises(HttpError):
        reader(gmail, sleeps).file("m1", "Label_7")

    assert sleeps == []


def test_given_a_refresh_token_when_credentials_are_built_then_they_refresh_on_first_use_with_three_scopes() -> None:
    credentials = gmail_auth.build_credentials("refresh-secret", "client-id", "client-secret")

    assert credentials.valid is False  # no access token yet, so the first call refreshes it
    assert credentials.refresh_token == "refresh-secret"  # noqa: S105
    assert sorted(credentials.scopes or []) == sorted(gmail_auth.SCOPES)
    assert len(gmail_auth.SCOPES) == 3
    assert "https://mail.google.com/" not in gmail_auth.SCOPES


# ---- U-backlog-04: unread inbox mail before a cut-off (INT-003, AC-B1, AC-B2, AC-B3, AC-B9) ----------------------

CUTOFF = datetime(2026, 11, 8, 18, 0, tzinfo=timezone(timedelta(hours=1)))  # 17:00 UTC
CUTOFF_EPOCH = int(datetime(2026, 11, 8, 17, 0, tzinfo=UTC).timestamp())


def listed(gmail: FakeGmail) -> list[dict[str, Any]]:
    return [kw for name, kw in gmail.calls if name == "list" and "q" in kw]


def test_given_a_cutoff_when_unread_mail_is_listed_then_the_query_is_inbox_unread_before_epoch_without_own_mail(
    gmail: FakeGmail,
) -> None:
    gmail.message_pages = [{"messages": [{"id": "a"}]}]

    ids = reader(gmail).list_unread_before(CUTOFF)

    assert ids == ["a"]
    (request,) = listed(gmail)
    assert request["userId"] == "me"
    assert request["labelIds"] == ["INBOX", "UNREAD"]
    assert request["q"] == f"before:{CUTOFF_EPOCH} -in:sent"


def test_given_a_timezone_aware_cutoff_when_listed_then_it_is_converted_to_utc_epoch_seconds(gmail: FakeGmail) -> None:
    gmail.message_pages = [{}]

    reader(gmail).list_unread_before(CUTOFF)
    reader(gmail).list_unread_before(CUTOFF.astimezone(UTC))

    assert [kw["q"] for kw in listed(gmail)] == [f"before:{CUTOFF_EPOCH} -in:sent"] * 2


def test_given_a_naive_cutoff_when_listed_then_it_is_rejected_and_nothing_is_asked(gmail: FakeGmail) -> None:
    with pytest.raises(ValueError, match="timezone"):
        reader(gmail).list_unread_before(datetime(2026, 11, 8, 17, 0))  # noqa: DTZ001 - the point of the test

    assert gmail.calls == []


def test_given_three_pages_and_an_empty_last_page_when_listed_then_all_ids_come_back_in_gmails_order(
    gmail: FakeGmail,
) -> None:
    gmail.message_pages = [
        {"messages": [{"id": "new1"}, {"id": "new2"}], "nextPageToken": "1"},
        {"messages": [{"id": "mid"}], "nextPageToken": "2"},
        {},
    ]

    assert reader(gmail).list_unread_before(CUTOFF) == ["new1", "new2", "mid"]
    assert [kw.get("pageToken") for kw in listed(gmail)] == [None, "1", "2"]


def test_given_no_matching_mail_when_listed_then_the_list_is_empty(gmail: FakeGmail) -> None:
    gmail.message_pages = [{"resultSizeEstimate": 0}]

    assert reader(gmail).list_unread_before(CUTOFF) == []


def test_given_a_rate_limit_when_listed_then_it_is_retried_with_backoff(gmail: FakeGmail) -> None:
    gmail.message_pages = [[http_error(429, "rateLimitExceeded"), {"messages": [{"id": "a"}]}]]
    sleeps: list[float] = []

    assert reader(gmail, sleeps).list_unread_before(CUTOFF) == ["a"]
    assert len(sleeps) == 1


def test_given_the_listing_when_it_runs_then_it_only_lists_and_never_changes_or_deletes_anything(
    gmail: FakeGmail,
) -> None:
    gmail.message_pages = [{"messages": [{"id": "a"}]}]

    reader(gmail).list_unread_before(CUTOFF)

    assert {name for name, _ in gmail.calls} == {"list"}


def test_given_a_fetched_mail_when_read_then_it_carries_its_gmail_labels(gmail: FakeGmail) -> None:
    gmail.messages["m1"] = {
        "id": "m1",
        "threadId": "t1",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": "a@b.c"}],
            "body": {"data": b64("hi")},
        },
    }

    assert reader(gmail).fetch("m1").labels == frozenset({"INBOX", "UNREAD"})
