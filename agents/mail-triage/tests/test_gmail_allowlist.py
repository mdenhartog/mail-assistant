"""U-mail-categories-06, criteria 4 and 5 (AC-28, ADR-0046 item 6): the resort adapter allows only listed operations.

The allow-list lives in this test on purpose: adding a public operation to the adapter fails here until a person
changes the list, with the ADR in hand. Gmail's own rules are modelled by ``FakeGmail`` from knowledge of the API, not
checked against a real mailbox.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.adapters import gmail_resort
from app.adapters.gmail_resort import GmailResort, LabelNameTaken, LabelRefused
from app.core.scope import ArchiveLabel
from tests.fakes.fake_gmail import FakeGmail

# Spec AC-28: list, read, add label, remove label, create label, rename label by id.
ALLOWED = {
    "list_labels": "list",
    "list_mail": "list",
    "read_mail": "read",
    "count_mail": "read",
    "add_label": "add label",
    "remove_label": "remove label",
    "create_label": "create label",
    "rename_label": "rename label",
    "create_archive_label": "create the archive label",
    "rename_archive_label": "rename the archive label by id",
}
SOURCE = Path(inspect.getsourcefile(gmail_resort) or "").read_text(encoding="utf-8")


def resort(gmail: FakeGmail) -> GmailResort:
    return GmailResort(gmail, ArchiveLabel("Archive"), sleep=lambda _seconds: None)


def test_given_the_adapter_when_its_public_operations_are_listed_then_they_equal_the_allow_list() -> None:
    public = {name for name, _ in inspect.getmembers(GmailResort, callable) if not name.startswith("_")}

    assert public == set(ALLOWED)


@pytest.mark.parametrize("word", ["trash", "delete", "spam", "batchDelete", "untrash", "send", "insert"])
def test_given_the_module_source_when_scanned_then_it_has_no_forbidden_gmail_operation(word: str) -> None:
    assert word.lower() not in SOURCE.lower()


def test_given_the_adapter_when_used_then_the_gmail_service_only_sees_allowed_calls() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    mail = gmail.add_mail()
    adapter = resort(gmail)

    adapter.list_labels()
    adapter.count_mail(label)
    adapter.list_mail(label)
    adapter.read_mail(mail)
    adapter.add_label(mail, label)
    adapter.remove_label(mail, label)
    adapter.create_archive_label("Archive")
    adapter.rename_label(label, "Assistant/Invoices")

    allowed = {"labels.list", "labels.get", "labels.create", "labels.patch", "messages.list", "messages.get"}
    assert set(gmail.calls) <= allowed | {"messages.modify"}


def test_given_a_name_only_change_when_renamed_by_id_then_the_label_keeps_its_id_and_its_mail() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    mail = gmail.add_mail(labels=(label,))

    resort(gmail).rename_label(label, "Assistant/Invoices")

    assert gmail.label_table[label] == "Assistant/Invoices"
    assert label in gmail.mail_table[mail].labels


def test_given_a_new_name_that_a_label_already_has_when_renamed_then_it_is_reported_as_taken() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    gmail.add_label("Assistant/Invoices")

    with pytest.raises(LabelNameTaken):
        resort(gmail).rename_label(label, "Assistant/INVOICES")

    assert gmail.label_table[label] == "Assistant/Bills"


@pytest.mark.parametrize("source", ["Archive", "archive", "INBOX", "Work", "Assistant/Other"])
def test_given_a_label_that_is_not_a_category_label_when_renamed_then_it_is_refused(source: str) -> None:
    gmail = FakeGmail()
    gmail.add_label("Work")
    gmail.add_label("Archive")
    gmail.add_label("Assistant/Other")
    label = gmail.label_id(source) if source in gmail.label_names() else gmail.label_id(source.title())
    before = dict(gmail.label_table)

    with pytest.raises(LabelRefused):
        resort(gmail).rename_label(label, "Assistant/Renamed")

    assert gmail.label_table == before
    assert "labels.patch" not in gmail.calls


@pytest.mark.parametrize(
    "target", ["Archive", "Work", "INBOX", "Assistant/", "Assistant/Other", "Assistant/Archive", ""]
)
def test_given_a_target_name_outside_the_category_rules_when_renamed_then_it_is_refused(target: str) -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")

    with pytest.raises(LabelRefused):
        resort(gmail).rename_label(label, target)

    assert gmail.label_table[label] == "Assistant/Bills"


def test_given_a_nested_target_name_when_renamed_then_the_label_takes_it() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")

    resort(gmail).rename_label(label, "Assistant/Huis/Energie")

    assert gmail.label_table[label] == "Assistant/Huis/Energie"


@pytest.mark.parametrize(
    "target",
    [
        "Assistant/Archive/Old",
        "Assistant/other/x",
        "Assistant//b",
        "Assistant/a//b",
        "Assistant/a/",
        "/Assistant/a",
        "Assistant/a/../b",
        "Assistant/" + "a" * 216,
    ],
    ids=[
        "archive-first",
        "other-first",
        "empty-first",
        "empty-middle",
        "trailing-slash",
        "leading-slash",
        "dotdot",
        "226",
    ],
)
def test_given_a_nested_target_outside_the_v2_rules_when_renamed_then_it_is_refused(target: str) -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")

    with pytest.raises(LabelRefused):
        resort(gmail).rename_label(label, target)

    assert gmail.label_table[label] == "Assistant/Bills"


def test_given_a_nested_source_label_when_renamed_then_it_is_a_category_label_and_changes() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Huis/Energie")

    resort(gmail).rename_label(label, "Assistant/Huis/Gas")

    assert gmail.label_table[label] == "Assistant/Huis/Gas"


def test_given_a_label_of_225_characters_when_renamed_to_then_it_is_taken() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    target = "Assistant/" + "/".join(["a" * 40] * 5) + "/" + "a" * 10

    assert len(target) == 225
    resort(gmail).rename_label(label, target)

    assert gmail.label_table[label] == target


@pytest.mark.parametrize(
    "name", ["Work", "INBOX", "Assistant/", "assistant/x", "Foo/Archive", "Archived", "../Assistant/x", "Archive"]
)
def test_given_a_name_the_adapter_may_not_create_when_created_then_it_is_refused(name: str) -> None:
    gmail = FakeGmail()

    with pytest.raises(LabelRefused):
        resort(gmail).create_label(name)

    assert "labels.create" not in gmail.calls


@pytest.mark.parametrize("name", ["Assistant/Bills", "Assistant/Other"])
def test_given_a_name_the_adapter_may_create_when_created_then_the_label_exists(name: str) -> None:
    gmail = FakeGmail()

    label = resort(gmail).create_label(name)

    assert gmail.label_table[label.id] == name


def test_given_an_overlapping_run_made_the_label_first_when_created_then_the_existing_label_is_returned() -> None:
    gmail = FakeGmail()
    gmail.race_on_create("Archive")

    label = resort(gmail).create_archive_label("Archive")

    assert gmail.label_names().count("Archive") == 1
    assert gmail.label_table[label.id] == "Archive"


@pytest.mark.parametrize("target", ["Archive", "Work", "INBOX", "SPAM", "TRASH", "UNKNOWN_ID"])
@pytest.mark.parametrize("operation", ["add_label", "remove_label"])
def test_given_a_label_that_is_not_a_category_label_when_added_to_or_removed_from_mail_then_it_is_refused(
    operation: str, target: str
) -> None:
    gmail = FakeGmail()
    gmail.add_label("Work")
    gmail.add_label("Archive")
    mail = gmail.add_mail(labels=("INBOX",))
    label = gmail.label_id(target) if target in gmail.label_names() else target
    before = set(gmail.mail_table[mail].labels)

    with pytest.raises(LabelRefused):
        getattr(resort(gmail), operation)(mail, label)

    assert gmail.mail_table[mail].labels == before
    assert "messages.modify" not in gmail.calls


def test_given_a_category_label_when_added_and_removed_then_only_that_label_changes() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    mail = gmail.add_mail(labels=("INBOX", "UNREAD"))
    adapter = resort(gmail)

    adapter.add_label(mail, label)
    assert gmail.mail_table[mail].labels == {"INBOX", "UNREAD", label}
    assert adapter.read_mail(mail) == {"INBOX", "UNREAD", label}
    adapter.remove_label(mail, label)

    assert gmail.mail_table[mail].labels == {"INBOX", "UNREAD"}


def test_given_labels_when_listed_then_ids_names_and_mail_per_label_come_back() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    first = gmail.add_mail(labels=("INBOX", label))
    second = gmail.add_mail(labels=(label,))
    gmail.add_mail()
    adapter = resort(gmail)

    labels = {item.name: item.id for item in adapter.list_labels()}

    assert labels["Assistant/Bills"] == label
    assert labels["INBOX"] == "INBOX"
    assert adapter.count_mail(label) == 2
    assert set(adapter.list_mail(label)) == {first, second}
    assert adapter.list_mail(gmail.add_label("Assistant/Empty")) == []


def test_given_a_label_that_was_renamed_by_the_user_in_gmail_when_listed_again_then_the_guard_follows() -> None:
    gmail = FakeGmail()
    label = gmail.add_label("Assistant/Bills")
    mail = gmail.add_mail()
    adapter = resort(gmail)
    adapter.list_labels()
    gmail.label_table[label] = "Archive"  # the user renames it in Gmail

    adapter.list_labels()

    with pytest.raises(LabelRefused):
        adapter.add_label(mail, label)


def test_given_the_default_archive_label_when_mail_is_filed_or_unfiled_there_then_the_adapter_refuses() -> None:
    gmail = FakeGmail()
    archive = gmail.add_label("Assistant/Archive")
    mail = gmail.add_mail(("INBOX",))
    adapter = GmailResort(gmail, ArchiveLabel("Assistant/Archive"), sleep=lambda _seconds: None)

    with pytest.raises(LabelRefused):
        adapter.add_label(mail, archive)
    with pytest.raises(LabelRefused):
        adapter.remove_label(mail, archive)


@pytest.mark.parametrize("archive", ["Assistant/Archive", "Bewaard", "Mail/Done"])
def test_given_a_usable_archive_name_when_the_archive_label_is_created_then_it_is_allowed_and_other_names_are_not(
    archive: str,
) -> None:
    gmail = FakeGmail()
    adapter = GmailResort(gmail, ArchiveLabel(archive), sleep=lambda _seconds: None)

    adapter.create_archive_label(archive)

    assert archive in gmail.label_names()
    with pytest.raises(LabelRefused):
        adapter.create_label("Archive")


UNUSABLE = ["", " Bewaard", "a..b", "INBOX", "spam", "CATEGORY_X", "Assistant/Other", "Assistant/Travel", "Mail//x"]


@pytest.mark.parametrize("name", UNUSABLE)
def test_given_an_unusable_archive_name_when_the_archive_label_is_created_then_it_is_refused_before_the_call(
    name: str,
) -> None:
    gmail = FakeGmail()

    with pytest.raises(LabelRefused):
        resort(gmail).create_archive_label(name)

    assert gmail.calls == []


def archive_adapter(gmail: FakeGmail) -> tuple[GmailResort, str]:
    archive_id = gmail.add_label("Archive")
    adapter = GmailResort(gmail, ArchiveLabel("Archive", archive_id), sleep=lambda _seconds: None)
    return adapter, archive_id


def test_given_the_archive_label_id_when_renamed_to_a_usable_name_then_it_keeps_its_id_and_its_mail() -> None:
    gmail = FakeGmail()
    adapter, archive_id = archive_adapter(gmail)
    mail = gmail.add_mail(labels=(archive_id,))

    adapter.rename_archive_label(archive_id, "Bewaard")

    assert gmail.label_table[archive_id] == "Bewaard"
    assert archive_id in gmail.mail_table[mail].labels


@pytest.mark.parametrize("target", ["Assistant/Bills", "Work", "INBOX", "UNKNOWN_ID"])
def test_given_a_label_that_is_not_the_archive_label_when_renamed_as_the_archive_then_it_is_refused(
    target: str,
) -> None:
    gmail = FakeGmail()
    adapter, _ = archive_adapter(gmail)
    gmail.add_label("Work")
    gmail.add_label("Assistant/Bills")
    label = gmail.label_id(target) if target in gmail.label_names() else target
    before = dict(gmail.label_table)

    with pytest.raises(LabelRefused):
        adapter.rename_archive_label(label, "Bewaard")

    assert gmail.label_table == before
    assert "labels.patch" not in gmail.calls


@pytest.mark.parametrize("name", UNUSABLE)
def test_given_the_archive_label_when_renamed_to_an_unusable_name_then_it_is_refused_before_the_call(
    name: str,
) -> None:
    gmail = FakeGmail()
    adapter, archive_id = archive_adapter(gmail)

    with pytest.raises(LabelRefused):
        adapter.rename_archive_label(archive_id, name)

    assert gmail.label_table[archive_id] == "Archive"
    assert "labels.patch" not in gmail.calls


def test_given_the_archive_label_id_when_renamed_through_the_category_rename_then_it_is_refused() -> None:
    gmail = FakeGmail()
    adapter, archive_id = archive_adapter(gmail)

    with pytest.raises(LabelRefused):
        adapter.rename_label(archive_id, "Assistant/Renamed")

    assert "labels.patch" not in gmail.calls


def test_given_a_renamed_archive_label_when_mail_is_filed_or_unfiled_there_then_the_adapter_still_refuses() -> None:
    gmail = FakeGmail()
    adapter, archive_id = archive_adapter(gmail)
    mail = gmail.add_mail(("INBOX",))
    adapter.rename_archive_label(archive_id, "Assistant/Archive")  # allowed: exactly the default name

    with pytest.raises(LabelRefused):
        adapter.add_label(mail, archive_id)
    with pytest.raises(LabelRefused):
        adapter.remove_label(mail, archive_id)
