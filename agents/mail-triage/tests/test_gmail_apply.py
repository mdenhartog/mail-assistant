"""U-mail-categories-22, open point (c): the real ``ApplyMailbox`` on the Gmail double.

A deleted mail is ``None`` (read) or ``MailGone`` (write); any other Gmail failure on a mail is ``MailFailed``; the
label guards of the narrow adapter stay in force (label creation is in ``tests/adapters/test_gmail_apply_labels.py``).
"""

from __future__ import annotations

import pytest

from app.adapters.gmail_apply import GmailApply
from app.core.managed import ManagedLabel, ManagedSet, Role
from app.usecases.resort_apply import MailFailed, MailGone
from tests.fakes.fake_gmail import FakeGmail


def _apply(gmail: FakeGmail) -> GmailApply:
    managed = [
        ManagedLabel(name, label_id, Role.TOPIC)
        for label_id, name in gmail.label_table.items()
        if label_id.startswith("Label_")
    ]
    return GmailApply(gmail, ManagedSet(managed), sleep=lambda _seconds: None)


def test_add_and_remove_label_change_only_that_label() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Finance")
    travel = gmail.add_label("Travel")
    mid = gmail.add_mail(("INBOX", finance))
    mailbox = _apply(gmail)

    mailbox.add_label(mid, travel)
    mailbox.remove_label(mid, finance)

    assert gmail.mail_table[mid].labels == {"INBOX", travel}


def test_a_deleted_mail_is_none_when_read_and_mail_gone_when_written() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Finance")
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
    finance = gmail.add_label("Finance")
    mid = gmail.add_mail(("INBOX",))
    mailbox = _apply(gmail)
    mailbox.label_names()  # the label names are known, so the failure hits the change itself

    gmail.fail_next(403)
    with pytest.raises(MailFailed):
        mailbox.add_label(mid, finance)
    gmail.fail_next(403)
    with pytest.raises(MailFailed):
        mailbox.fetch(mid)


def test_the_guards_of_the_narrow_adapter_hold_an_unmanaged_label_is_refused() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail(("INBOX",))

    with pytest.raises(MailFailed):
        _apply(gmail).remove_label(mid, "INBOX")
    assert gmail.mail_table[mid].labels >= {"INBOX"}
    assert "messages.modify" not in gmail.calls


def test_count_mail_is_the_number_of_mails_with_the_label() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Finance")
    for _ in range(3):
        gmail.add_mail(("INBOX", finance))
    gmail.add_mail(("INBOX",))

    assert _apply(gmail).count_mail(finance) == 3


def test_the_label_names_map_ids_to_names() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Finance")

    assert _apply(gmail).label_names()[finance] == "Finance"
