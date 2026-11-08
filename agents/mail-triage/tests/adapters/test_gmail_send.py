"""U-06: sending a confirmed reply (AC-7, AC-16, AC-28, AC-29; threat model T-02, T-14, T-15)."""

from __future__ import annotations

import base64
from email import message_from_bytes
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from app.adapters import gmail_send
from app.adapters.gmail_read import FetchedMail
from app.adapters.gmail_send import ConfirmedDraft, GmailSender, NotRepliableError, SenderMismatchError

if TYPE_CHECKING:
    from email.message import Message

SOURCE = Path(gmail_send.__file__).read_text(encoding="utf-8")
ME_ADDRESS = "marco@example.com"


class Request:
    def __init__(self, result: Any) -> None:
        self.result = result

    def execute(self) -> Any:
        return self.result


class FakeGmail:
    def __init__(self, already_sent: bool = False) -> None:
        self.already_sent = already_sent
        self.sent: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []

    def users(self) -> FakeGmail:
        return self

    def getProfile(self, **kw: Any) -> Request:  # noqa: N802
        return Request({"emailAddress": ME_ADDRESS})

    def messages(self) -> FakeGmail:
        return self

    def list(self, **kw: Any) -> Request:
        self.queries.append(kw)
        return Request({"messages": [{"id": "already-1"}]} if self.already_sent else {})

    def send(self, **kw: Any) -> Request:
        self.sent.append(kw)
        return Request({"id": "sent-1", "threadId": kw["body"]["threadId"]})


def original(**changes: Any) -> FetchedMail:
    headers = {"From": "Anna <anna@example.com>", "Subject": "Dinner?", "Message-ID": "<abc@example.com>"}
    headers.update(changes.pop("headers", {}))
    base = {
        "message_id": "m1",
        "thread_id": "t1",
        "sender": "anna@example.com",
        "reply_to": None,
        "subject": "Dinner?",
        "text": "Are you free?",
        "has_attachment": False,
        "headers": headers,
    }
    return FetchedMail(**{**base, **changes})


def draft(**changes: Any) -> ConfirmedDraft:
    values = {"draft_id": "d-1", "sender": ME_ADDRESS, "recipient": None, "body": "Yes, Friday works.\nMarco"}
    return ConfirmedDraft(**{**values, **changes})


def parsed(gmail: FakeGmail) -> tuple[Message, dict[str, Any]]:
    request = gmail.sent[0]
    raw = base64.urlsafe_b64decode(request["body"]["raw"])
    return message_from_bytes(raw), request


def test_given_a_confirmed_draft_when_sent_then_it_goes_in_the_same_thread_with_reply_headers() -> None:
    gmail = FakeGmail()

    sent_id = GmailSender(gmail).send_reply(original(), draft())

    message, request = parsed(gmail)
    assert sent_id == "sent-1"
    assert request["body"]["threadId"] == "t1"
    assert message["To"] == "anna@example.com"
    assert message["From"] == ME_ADDRESS
    assert message["Subject"] == "Re: Dinner?"
    assert message["In-Reply-To"] == "<abc@example.com>"
    assert message["References"] == "<abc@example.com>"
    assert message["Message-ID"].startswith("<mail-triage-d-1@")


def test_given_a_subject_that_already_starts_with_re_when_replying_then_it_is_not_doubled() -> None:
    gmail = FakeGmail()

    GmailSender(gmail).send_reply(original(subject="Re: Dinner?"), draft())

    assert parsed(gmail)[0]["Subject"] == "Re: Dinner?"


def test_given_a_reply_to_that_differs_from_from_when_replying_then_the_recipient_is_from() -> None:
    gmail = FakeGmail()

    GmailSender(gmail).send_reply(original(reply_to="attacker@example.org"), draft())

    assert parsed(gmail)[0]["To"] == "anna@example.com"


def test_given_marco_names_another_recipient_when_replying_then_that_address_is_used() -> None:
    gmail = FakeGmail()

    GmailSender(gmail).send_reply(original(reply_to="other@example.org"), draft(recipient="other@example.org"))

    assert parsed(gmail)[0]["To"] == "other@example.org"


@pytest.mark.parametrize(
    "headers",
    [
        {"Auto-Submitted": "auto-generated"},
        {"Auto-Submitted": "auto-replied"},
        {"List-Id": "<news.example.com>"},
        {"Precedence": "bulk"},
        {"Precedence": "list"},
    ],
)
def test_given_an_automatic_or_list_mail_when_a_reply_is_requested_then_nothing_is_sent(
    headers: dict[str, str],
) -> None:
    gmail = FakeGmail()

    with pytest.raises(NotRepliableError):
        GmailSender(gmail).send_reply(original(headers=headers), draft())

    assert gmail.sent == []


@pytest.mark.parametrize(
    "sender", ["noreply@example.com", "no-reply@example.com", "donotreply@example.com", "MAILER-DAEMON@example.com"]
)
def test_given_a_noreply_sender_when_a_reply_is_requested_then_nothing_is_sent(sender: str) -> None:
    gmail = FakeGmail()

    with pytest.raises(NotRepliableError):
        GmailSender(gmail).send_reply(original(sender=sender), draft())

    assert gmail.sent == []


def test_given_auto_submitted_no_when_replying_then_it_is_a_normal_mail_and_is_sent() -> None:
    gmail = FakeGmail()

    GmailSender(gmail).send_reply(original(headers={"Auto-Submitted": "no"}), draft())

    assert len(gmail.sent) == 1


def test_given_a_sender_other_than_the_authenticated_address_when_sending_then_it_refuses() -> None:
    gmail = FakeGmail()

    with pytest.raises(SenderMismatchError):
        GmailSender(gmail).send_reply(original(), draft(sender="someone-else@example.com"))

    assert gmail.sent == []


def test_given_a_draft_that_was_already_sent_when_sent_again_then_no_duplicate_goes_out() -> None:
    gmail = FakeGmail(already_sent=True)

    sent_id = GmailSender(gmail).send_reply(original(), draft())

    assert sent_id == "already-1"
    assert gmail.sent == []
    assert "rfc822msgid:" in gmail.queries[0]["q"]
    assert gmail.queries[0]["labelIds"] == ["SENT"]


@pytest.mark.parametrize("bad", ["a@example.com\nBcc: x@example.org", "a@example.com\r\nSubject: x"])
def test_given_a_header_injection_attempt_when_building_the_mail_then_it_is_refused(bad: str) -> None:
    gmail = FakeGmail()

    with pytest.raises(ValueError, match="header"):
        GmailSender(gmail).send_reply(original(), draft(recipient=bad))

    assert gmail.sent == []


@pytest.mark.parametrize("word", ["trash", "delete", "spam", "untrash"])
def test_given_the_module_source_when_scanned_then_it_has_no_trash_delete_or_spam_operation(word: str) -> None:
    assert word.lower() not in SOURCE.lower()
