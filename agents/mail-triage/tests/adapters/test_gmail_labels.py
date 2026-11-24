"""U-label-prefix-removal-04: the Gmail adapters change labels only for managed ids (ADR-0060, AC 3, 19, 29, 31).

``FakeGmail`` models Gmail's rules from knowledge of the API (409 on a name clash, 400 on a refused name, 400 on a
deleted label id in a change, 404 on a deleted label id in a patch); it is not checked against a real mailbox.
"""

from __future__ import annotations

import logging

import pytest
from googleapiclient.errors import HttpError

from app.adapters.gmail_read import GmailLabelError, GmailReader, LabelNameRejected, LabelNameTaken, LabelRefused
from app.adapters.gmail_resort import GmailResort
from app.core.managed import ManagedLabel, ManagedSet, Role
from tests.fakes.fake_gmail import FakeGmail

CANARY = "Canary-Label-8841"


def topic(name: str, label_id: str | None = None) -> ManagedLabel:
    return ManagedLabel(name, label_id, Role.TOPIC)


def resort(gmail: FakeGmail, *labels: ManagedLabel) -> GmailResort:
    return GmailResort(gmail, ManagedSet(labels), sleep=lambda _seconds: None)


# --- criterion 1: add and remove only for managed ids ------------------------------------------------------------


@pytest.mark.parametrize("operation", ["add_label", "remove_label"])
@pytest.mark.parametrize("target", ["Work", "INBOX", "SPAM", "UNKNOWN_ID"])
def test_given_a_label_that_is_not_managed_when_added_or_removed_then_it_is_refused_and_gmail_is_not_called(
    operation: str, target: str
) -> None:
    gmail = FakeGmail()
    work = gmail.add_label("Work")
    bills = gmail.add_label("Bills")
    mail = gmail.add_mail(labels=("INBOX",))
    label = work if target == "Work" else target
    adapter = resort(gmail, topic("Bills", bills))
    before = set(gmail.mail_table[mail].labels)
    gmail.calls.clear()

    with pytest.raises(LabelRefused):
        getattr(adapter, operation)(mail, label)

    assert gmail.calls == []
    assert gmail.mail_table[mail].labels == before


@pytest.mark.parametrize("operation", ["add_label", "remove_label"])
def test_given_the_archive_label_when_added_or_removed_then_it_is_refused_as_the_agent_never_files_there(
    operation: str,
) -> None:
    gmail = FakeGmail()
    archive = gmail.add_label("Archive")
    mail = gmail.add_mail(labels=("INBOX",))
    adapter = resort(gmail, ManagedLabel("Archive", archive, Role.ARCHIVE))

    with pytest.raises(LabelRefused):
        getattr(adapter, operation)(mail, archive)

    assert gmail.calls == []


def test_given_a_managed_label_when_added_and_removed_then_only_that_label_changes() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    mail = gmail.add_mail(labels=("INBOX", "UNREAD"))
    adapter = resort(gmail, topic("Bills", bills))

    assert adapter.add_label(mail, bills) == bills
    assert gmail.mail_table[mail].labels == {"INBOX", "UNREAD", bills}
    adapter.remove_label(mail, bills)

    assert gmail.mail_table[mail].labels == {"INBOX", "UNREAD"}


def test_given_a_managed_label_without_a_stored_id_when_listed_then_it_is_matched_by_name_until_id_known() -> (
    None
):
    gmail = FakeGmail()
    bills = gmail.add_label("bills")
    mail = gmail.add_mail()
    adapter = resort(gmail, topic("Bills"))
    adapter.list_labels()

    adapter.add_label(mail, bills)

    assert bills in gmail.mail_table[mail].labels


def test_given_an_unmanaged_label_when_created_or_renamed_then_it_is_refused_and_gmail_is_not_called() -> None:
    gmail = FakeGmail()
    work = gmail.add_label("Work")
    adapter = resort(gmail, topic("Bills", gmail.add_label("Bills")))
    gmail.calls.clear()

    with pytest.raises(LabelRefused):
        adapter.create_label(topic("Taxes"))
    with pytest.raises(LabelRefused):
        adapter.rename_label(work, "Taxes")

    assert gmail.calls == []
    assert gmail.label_names().count("Taxes") == 0


def test_given_the_reader_when_a_label_is_not_managed_then_it_is_refused_before_any_call() -> None:
    gmail = FakeGmail()
    mail = gmail.add_mail()
    reader = GmailReader(gmail, sleep=lambda _seconds: None)
    gmail.calls.clear()

    with pytest.raises(LabelRefused):
        reader.file(mail, "Label_9")
    with pytest.raises(LabelRefused):
        reader.add_label(mail, "Label_9")

    assert gmail.calls == []


def test_given_the_reader_with_a_managed_label_when_filing_then_the_label_is_added_and_the_inbox_removed() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    mail = gmail.add_mail()
    reader = GmailReader(gmail, managed=ManagedSet([topic("Bills", bills)]), sleep=lambda _seconds: None)

    reader.file(mail, bills)

    assert gmail.mail_table[mail].labels == {bills}


# --- criterion 2: create by list name adopts an existing label ---------------------------------------------------


def test_given_a_category_named_like_a_label_with_mail_when_created_then_the_label_is_adopted_and_mail_untouched() -> (
    None
):
    gmail = FakeGmail()
    existing = gmail.add_label("Amerika")
    mail = gmail.add_mail(labels=("INBOX", existing))
    adapter = resort(gmail, topic("Amerika"))

    first = adapter.create_label(topic("Amerika"))
    second = adapter.create_label(topic("Amerika"))

    assert first.id == second.id == existing
    assert gmail.label_names().count("Amerika") == 1
    assert gmail.mail_table[mail].labels == {"INBOX", existing}
    assert "messages.modify" not in gmail.calls


def test_given_an_adopted_label_when_used_then_it_is_managed_from_then_on() -> None:
    gmail = FakeGmail()
    existing = gmail.add_label("amerika")
    mail = gmail.add_mail()
    adapter = resort(gmail, topic("Amerika"))

    adapter.create_label(topic("Amerika"))
    adapter.add_label(mail, existing)

    assert existing in gmail.mail_table[mail].labels


def test_given_a_missing_label_when_created_then_it_exists_and_a_second_run_that_raced_it_is_adopted() -> None:
    gmail = FakeGmail()
    gmail.race_on_create("Taxes")

    label = resort(gmail, topic("Taxes")).create_label(topic("Taxes"))

    assert gmail.label_names().count("Taxes") == 1
    assert gmail.label_table[label.id] == "Taxes"


def test_given_the_reader_when_a_managed_label_is_ensured_then_an_existing_one_is_adopted() -> None:
    gmail = FakeGmail()
    existing = gmail.add_label("Amerika")
    reader = GmailReader(gmail, managed=ManagedSet([topic("Amerika")]), sleep=lambda _seconds: None)

    assert reader.ensure_label(topic("Amerika")) == existing
    assert gmail.label_names().count("Amerika") == 1


# --- criterion 3: rename patches only the given id ---------------------------------------------------------------


def test_given_a_rename_by_id_when_made_then_only_that_id_is_patched() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    other = gmail.add_label("Other")
    mail = gmail.add_mail(labels=(bills,))
    adapter = resort(gmail, topic("Bills", bills), ManagedLabel("Other", other, Role.OTHER))
    before = dict(gmail.label_table)
    gmail.calls.clear()

    result = adapter.rename_label(bills, "Invoices")

    assert result.id == bills
    assert gmail.calls == ["labels.patch"]
    assert gmail.label_table == {**before, bills: "Invoices"}
    assert bills in gmail.mail_table[mail].labels


def test_given_the_archive_label_when_renamed_to_a_usable_name_then_it_keeps_its_id_and_mail() -> None:
    gmail = FakeGmail()
    archive = gmail.add_label("Archive")
    mail = gmail.add_mail(labels=(archive,))
    adapter = resort(gmail, ManagedLabel("Archive", archive, Role.ARCHIVE))

    adapter.rename_label(archive, "Bewaard")

    assert gmail.label_table[archive] == "Bewaard"
    assert archive in gmail.mail_table[mail].labels


@pytest.mark.parametrize("target", ["", "a..b", "INBOX", "Mail//x", " Bills", "x/"])
def test_given_a_new_name_outside_the_rules_when_renamed_then_it_is_refused_before_the_call(target: str) -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    adapter = resort(gmail, topic("Bills", bills))
    gmail.calls.clear()

    with pytest.raises(LabelRefused):
        adapter.rename_label(bills, target)

    assert gmail.calls == []


# --- criteria 4 and 5: codes and status, never a label name ------------------------------------------------------


def test_given_a_409_for_a_name_clash_when_logged_then_the_log_has_status_and_reason_and_no_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gmail = FakeGmail()
    gmail.add_label(CANARY)
    adapter = resort(gmail, topic(CANARY))

    with caplog.at_level(logging.DEBUG):
        adapter.create_label(topic(CANARY))

    assert "409" in caplog.text
    assert "labelNameExists" in caplog.text
    assert CANARY not in caplog.text


def test_given_a_refused_name_when_created_then_the_error_has_the_status_and_no_name() -> None:
    gmail = FakeGmail()
    gmail.refuse_name(CANARY)

    with pytest.raises(LabelNameRejected) as raised:
        resort(gmail, topic(CANARY)).create_label(topic(CANARY))

    assert "400" in str(raised.value)
    assert CANARY not in str(raised.value)
    assert raised.value.__cause__ is None


def test_given_a_name_taken_when_renamed_then_the_error_has_the_status_and_no_name() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    gmail.add_label(CANARY)

    with pytest.raises(LabelNameTaken) as raised:
        resort(gmail, topic("Bills", bills)).rename_label(bills, CANARY.upper())

    assert "409" in str(raised.value)
    assert CANARY.upper() not in str(raised.value)
    assert CANARY not in str(raised.value)


def test_given_any_other_gmail_error_when_a_label_is_created_then_the_error_has_status_and_reason_and_no_name() -> None:
    gmail = FakeGmail()
    gmail.fail_next(403)

    with pytest.raises(GmailLabelError) as raised:
        resort(gmail, topic(CANARY)).create_label(topic(CANARY))

    assert raised.value.status == 403
    assert "403" in str(raised.value)
    assert CANARY not in str(raised.value)
    assert raised.value.__cause__ is None


def test_given_a_refusal_when_raised_then_the_message_is_a_code_without_the_label_name() -> None:
    gmail = FakeGmail()
    canary = gmail.add_label(CANARY)
    adapter = resort(gmail, topic("Bills"))
    adapter.list_labels()

    with pytest.raises(LabelRefused) as raised:
        adapter.add_label("m1", canary)
    with pytest.raises(LabelRefused) as created:
        adapter.create_label(topic(CANARY))
    with pytest.raises(LabelRefused) as renamed:
        adapter.rename_label(canary, "Bills2")

    for error in (raised, created, renamed):
        assert CANARY not in str(error.value)
        assert str(error.value).isidentifier()


# --- criterion 7: a label deleted by hand is recreated once ------------------------------------------------------


def test_given_a_stored_id_that_was_deleted_by_hand_when_ensured_then_it_is_recreated_once_with_a_new_id() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Bills")
    gmail.delete_label(old)
    adapter = resort(gmail, topic("Bills", old))

    made = adapter.ensure_label(topic("Bills", old))
    again = adapter.ensure_label(topic("Bills", made.id))

    assert made.id != old
    assert again == made
    assert gmail.label_names().count("Bills") == 1
    assert gmail.calls.count("labels.create") == 1


def test_given_a_stored_id_that_exists_when_ensured_then_nothing_is_created() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")

    made = resort(gmail, topic("Bills", bills)).ensure_label(topic("Bills", bills))

    assert made.id == bills
    assert "labels.create" not in gmail.calls


def test_given_a_label_deleted_by_hand_when_mail_is_filed_under_it_then_it_is_recreated_and_the_new_id_returned() -> (
    None
):
    gmail = FakeGmail()
    old = gmail.add_label("Bills")
    mail = gmail.add_mail()
    adapter = resort(gmail, topic("Bills", old))
    adapter.list_labels()
    gmail.delete_label(old)

    used = adapter.add_label(mail, old)

    assert used != old
    assert gmail.mail_table[mail].labels == {"INBOX", used}
    assert gmail.calls.count("labels.create") == 1


def test_given_a_label_deleted_by_hand_when_it_is_removed_from_mail_then_nothing_is_recreated() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Bills")
    mail = gmail.add_mail()
    adapter = resort(gmail, topic("Bills", old))
    gmail.delete_label(old)

    adapter.remove_label(mail, old)

    assert "labels.create" not in gmail.calls


def test_given_a_label_deleted_by_hand_when_renamed_then_it_is_recreated_under_the_new_name() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Bills")
    adapter = resort(gmail, topic("Bills", old))
    gmail.delete_label(old)

    made = adapter.rename_label(old, "Invoices")

    assert made.id != old
    assert gmail.label_table[made.id] == "Invoices"
    assert gmail.calls.count("labels.create") == 1


def test_given_a_gmail_error_that_is_not_a_missing_label_when_adding_then_it_is_raised_as_it_was() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    mail = gmail.add_mail()
    adapter = resort(gmail, topic("Bills", bills))
    gmail.fail_next(403)

    with pytest.raises(HttpError):
        adapter.add_label(mail, bills)
