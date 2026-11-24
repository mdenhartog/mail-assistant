"""U-label-prefix-removal-04: the apply mailbox on the managed label guard (ADR-0060, AC 3, 19, 31).

Kept apart from the other adapter tests because ``GmailApply`` imports the ``MailFailed`` and ``MailGone`` port from
``app.usecases.resort_apply``, which unit 18 repairs.
"""

from __future__ import annotations

import pytest

from app.adapters.gmail_apply import GmailApply
from app.core.managed import ManagedLabel, ManagedSet, Role
from app.usecases.resort_apply import MailFailed, MailGone
from tests.fakes.fake_gmail import FakeGmail


def topic(name: str, label_id: str | None = None) -> ManagedLabel:
    return ManagedLabel(name, label_id, Role.TOPIC)


def test_given_the_apply_mailbox_when_a_managed_label_is_ensured_then_it_is_created_once_and_reused() -> None:
    gmail = FakeGmail()
    adapter = GmailApply(gmail, ManagedSet([topic("Travel")]), sleep=lambda _seconds: None)

    first = adapter.ensure_label(topic("Travel"))
    second = adapter.ensure_label(topic("Travel"))

    assert first == second == gmail.label_id("Travel")
    assert gmail.calls.count("labels.create") == 1


def test_given_the_apply_mailbox_when_an_unmanaged_label_is_ensured_then_it_fails_and_nothing_is_created() -> None:
    gmail = FakeGmail()
    adapter = GmailApply(gmail, ManagedSet([topic("Travel")]), sleep=lambda _seconds: None)

    with pytest.raises(MailFailed):
        adapter.ensure_label(topic("Work"))

    assert gmail.calls == []


def test_given_the_apply_mailbox_when_a_label_was_deleted_by_hand_then_it_is_recreated_without_a_crash() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Bills")
    gmail.delete_label(old)
    adapter = GmailApply(gmail, ManagedSet([topic("Bills", old)]), sleep=lambda _seconds: None)

    new_id = adapter.ensure_label(topic("Bills", old))

    assert gmail.label_table[new_id] == "Bills"


def test_given_an_unmanaged_label_when_added_or_removed_through_the_mailbox_then_it_fails_without_a_call() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail(("INBOX",))
    adapter = GmailApply(gmail, ManagedSet([topic("Travel")]), sleep=lambda _seconds: None)

    with pytest.raises(MailFailed):
        adapter.remove_label(mid, "INBOX")
    with pytest.raises(MailFailed):
        adapter.add_label(mid, "Label_99")

    assert gmail.calls == []


def test_given_a_mail_that_is_gone_when_a_managed_label_is_added_then_it_is_mail_gone() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    mid = gmail.add_mail(("INBOX",))
    adapter = GmailApply(gmail, ManagedSet([topic("Bills", bills)]), sleep=lambda _seconds: None)
    gmail.delete_mail(mid)

    with pytest.raises(MailGone):
        adapter.add_label(mid, bills)
