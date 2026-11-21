"""U-mail-categories-22, open point (c): the real ``ApplyMailbox`` on the Gmail double.

A deleted mail is ``None`` (read) or ``MailGone`` (write); any other Gmail failure on a mail is ``MailFailed``; the
label guards of the narrow adapter stay in force; ``ensure_label`` lists first and creates only a missing label.
"""

from __future__ import annotations

import pytest

from app.adapters.gmail_apply import GmailApply
from app.usecases.resort_apply import MailFailed, MailGone
from tests.fakes.fake_gmail import FakeGmail


def _apply(gmail: FakeGmail) -> GmailApply:
    return GmailApply(gmail, "Archive", sleep=lambda _seconds: None)


def test_ensure_label_returns_the_existing_label_without_creating_one() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")

    assert _apply(gmail).ensure_label("Assistant/Finance") == finance
    assert "labels.create" not in gmail.calls


def test_ensure_label_creates_a_missing_label_once_and_is_idempotent() -> None:
    gmail = FakeGmail()
    mailbox = _apply(gmail)

    first = mailbox.ensure_label("Assistant/Travel")
    second = mailbox.ensure_label("Assistant/Travel")

    assert first == second == gmail.label_id("Assistant/Travel")
    assert gmail.calls.count("labels.create") == 1


def test_ensure_label_survives_a_run_that_made_the_label_at_the_same_time() -> None:
    gmail = FakeGmail()
    gmail.race_on_create("Assistant/Travel")

    label_id = _apply(gmail).ensure_label("Assistant/Travel")

    assert label_id == gmail.label_id("Assistant/Travel")
    assert gmail.label_names().count("Assistant/Travel") == 1


def test_ensure_label_refuses_a_name_outside_the_assistant_labels() -> None:
    gmail = FakeGmail()

    with pytest.raises(MailFailed):
        _apply(gmail).ensure_label("Work")
    assert "Work" not in gmail.label_names()


def test_add_and_remove_label_change_only_that_label() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")
    travel = gmail.add_label("Assistant/Travel")
    mid = gmail.add_mail(("INBOX", finance))
    mailbox = _apply(gmail)

    mailbox.add_label(mid, travel)
    mailbox.remove_label(mid, finance)

    assert gmail.mail_table[mid].labels == {"INBOX", travel}


def test_a_deleted_mail_is_none_when_read_and_mail_gone_when_written() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")
    mid = gmail.add_mail(("INBOX",))
    mailbox = _apply(gmail)
    mailbox.label_names()
    gmail.delete_mail(mid)

    assert mailbox.fetch(mid) is None
    with pytest.raises(MailGone):
        mailbox.add_label(mid, finance)
    with pytest.raises(MailGone):
        mailbox.remove_label(mid, finance)


def test_another_failure_of_gmail_on_a_mail_is_mail_failed_not_mail_gone() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")
    mid = gmail.add_mail(("INBOX",))
    mailbox = _apply(gmail)
    mailbox.label_names()  # the label names are known, so the failure hits the change itself

    gmail.fail_next(403)
    with pytest.raises(MailFailed):
        mailbox.add_label(mid, finance)
    gmail.fail_next(403)
    with pytest.raises(MailFailed):
        mailbox.fetch(mid)


def test_the_guards_of_the_narrow_adapter_hold_a_label_outside_assistant_is_refused() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail(("INBOX",))

    with pytest.raises(MailFailed):
        _apply(gmail).remove_label(mid, "INBOX")
    assert gmail.mail_table[mid].labels >= {"INBOX"}
    assert "messages.modify" not in gmail.calls


def test_count_mail_is_the_number_of_mails_with_the_label() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")
    for _ in range(3):
        gmail.add_mail(("INBOX", finance))
    gmail.add_mail(("INBOX",))

    assert _apply(gmail).count_mail(finance) == 3


def test_the_label_names_map_ids_to_names() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")

    assert _apply(gmail).label_names()[finance] == "Assistant/Finance"
