"""U-label-prefix-removal-04, criterion 6 (AC 11, ADR-0060): the Gmail methods the agent may call, by reflection.

The allow-list lives in this test on purpose: a new Gmail call in an adapter fails here until a person changes the
list, with the ADR in hand. Exactly one delete is allowed, ``labels.delete`` by id, in ``gmail_label_delete``
(unit 07). There is no trash, no delete of mail and no send in the label and mail adapters.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.adapters import gmail_read
from app.adapters.gmail_label_delete import GmailLabelDelete
from app.adapters.gmail_read import LabelRefused
from app.adapters.gmail_resort import GmailResort
from app.core.managed import ManagedLabel, ManagedSet, Role
from app.usecases.list_sync import ListSync, MigrationState
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.list_store import FakeListStore

ALLOWED_CALLS = {
    "labels.list",
    "labels.get",
    "labels.create",
    "labels.patch",
    "messages.list",
    "messages.get",
    "messages.modify",
    "settings.filters",  # users.settings.filters.list, read only: the filters that add a label (unit 07)
    "history.list",
    "getProfile",
}
RESERVED_DELETE = "labels.delete"  # by id, one place only: GmailLabelDelete.delete (unit 07)
ALLOWED_METHODS = {
    "list_labels": "list",
    "list_mail": "list",
    "read_mail": "read",
    "count_mail": "read",
    "add_label": "add label",
    "remove_label": "remove label",
    "create_label": "create label (adopts an existing label of that name)",
    "ensure_label": "create label again when the stored id was deleted by hand",
    "rename_label": "rename label by id",
    "set_managed": "replace the managed set of the run",
}
# The public surface of the delete adapter (unit 07): three reads and the one delete by id.
DELETE_METHODS = {
    "read_label": "type, counts and children",
    "labels_in_filters": "the label ids that Gmail filters add",
    "has_mail_including_trash": "one mail on the label, spam and trash included",
    "delete": "labels.delete by id after the checks",
}
ADAPTERS = Path(inspect.getsourcefile(gmail_read) or "").parent
# gmail_apply is read as text: importing it needs the re-sort use case, which unit 18 repairs.
SOURCES = {
    name: (ADAPTERS / f"{name}.py").read_text(encoding="utf-8")
    for name in ("gmail_read", "gmail_resort", "gmail_apply", "gmail_label_delete")
}
CHAIN = re.compile(r"users\(\)\.(?:(\w+)\(\)\.)?(\w+)\(")


def called_in(source: str) -> set[str]:
    return {f"{resource}.{method}" if resource else method for resource, method in CHAIN.findall(source)}


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_given_an_adapter_source_when_scanned_then_every_gmail_call_is_on_the_allow_list(name: str) -> None:
    assert called_in(SOURCES[name]) <= ALLOWED_CALLS | {RESERVED_DELETE}


def test_given_the_adapters_when_scanned_then_at_most_one_delete_exists_and_it_is_the_label_delete() -> None:
    deletes = [call for source in SOURCES.values() for call in called_in(source) if "delete" in call.lower()]

    assert set(deletes) <= {RESERVED_DELETE}
    assert len(deletes) <= 1


@pytest.mark.parametrize("name", sorted(SOURCES))
@pytest.mark.parametrize(
    "pattern",
    [r"\.(send|trash|untrash|batchDelete|batchModify|insert|import_)\(", r"messages\(\)\.delete\(", r"drafts\(\)"],
)
def test_given_an_adapter_source_when_scanned_then_it_has_no_trash_delete_mail_or_send(name: str, pattern: str) -> None:
    assert re.search(pattern, SOURCES[name]) is None


def test_given_the_resort_adapter_when_its_public_operations_are_listed_then_they_equal_the_allow_list() -> None:
    public = {name for name, _ in inspect.getmembers(GmailResort, callable) if not name.startswith("_")}

    assert public == set(ALLOWED_METHODS)


def test_given_the_adapter_when_used_then_the_gmail_service_only_sees_allowed_calls() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    mail = gmail.add_mail(labels=("INBOX",))
    managed = ManagedSet([ManagedLabel("Bills", bills, Role.TOPIC), ManagedLabel("Taxes", None, Role.TOPIC)])
    adapter = GmailResort(gmail, managed, sleep=lambda _seconds: None)

    adapter.list_labels()
    adapter.count_mail(bills)
    adapter.list_mail(bills)
    adapter.read_mail(mail)
    adapter.add_label(mail, bills)
    adapter.remove_label(mail, bills)
    adapter.create_label(ManagedLabel("Taxes", None, Role.TOPIC))
    adapter.ensure_label(ManagedLabel("Bills", bills, Role.TOPIC))
    adapter.rename_label(bills, "Invoices")

    assert set(gmail.calls) <= ALLOWED_CALLS


def test_given_the_delete_adapter_when_its_public_operations_are_listed_then_they_equal_the_allow_list() -> None:
    public = {name for name, _ in inspect.getmembers(GmailLabelDelete, callable) if not name.startswith("_")}

    assert public == set(DELETE_METHODS)


def test_given_the_sources_when_scanned_then_labels_delete_is_called_in_the_delete_adapter_only() -> None:
    owners = [name for name, source in SOURCES.items() if RESERVED_DELETE in called_in(source)]

    assert owners == ["gmail_label_delete"]


def test_given_the_delete_adapter_when_it_runs_then_the_gmail_service_only_sees_allowed_calls() -> None:
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")

    GmailLabelDelete(gmail, sleep=lambda _seconds: None).delete(bills)

    assert {call for call in gmail.calls if "delete" in call} == {RESERVED_DELETE}
    assert set(gmail.calls) <= {"labels.list", "labels.get", "messages.list", "settings.filters.list", RESERVED_DELETE}


READ_ONLY = {"list_labels", "list_mail", "read_mail", "count_mail", "set_managed"}
_UNMANAGED_ATTEMPTS = {
    "add_label": lambda a, mail, label: a.add_label(mail, label),
    "remove_label": lambda a, mail, label: a.remove_label(mail, label),
    "create_label": lambda a, _mail, _label: a.create_label(ManagedLabel("Taxes", None, Role.TOPIC)),
    "ensure_label": lambda a, _mail, label: a.ensure_label(ManagedLabel("Taxes", label, Role.TOPIC)),
    "rename_label": lambda a, _mail, label: a.rename_label(label, "Taxes"),
}


async def test_given_the_list_chain_when_every_writing_method_is_tried_then_only_the_list_passes() -> None:
    """List, then managed set (the sync), then the guard in the adapter, then Gmail: walked end to end.

    The managed set is the one the sync hands the adapter, not one built in the test. A label of the user that is not
    on the list is refused by every writing method before Gmail sees a call; a label of the list is accepted.
    """
    gmail = FakeGmail()
    bills = gmail.add_label("Bills")
    private = gmail.add_label("Private")  # the user's own label, not on the list
    mail = gmail.add_mail(labels=("INBOX", bills, private))
    store = FakeListStore(migration=MigrationState.DONE)
    store.save_list(["Bills"])
    adapter = GmailResort(gmail, ManagedSet(()), sleep=lambda _seconds: None)
    await ListSync(adapter, store).run()
    writing = set(ALLOWED_METHODS) - READ_ONLY

    assert writing == set(_UNMANAGED_ATTEMPTS)  # a new writing method must be added to this walk
    gmail.calls.clear()
    for attempt in _UNMANAGED_ATTEMPTS.values():
        with pytest.raises(LabelRefused):
            attempt(adapter, mail, private)
    assert gmail.calls == []
    assert gmail.label_table[private] == "Private"

    adapter.remove_label(mail, bills)  # the label of the list passes the guard and reaches Gmail
    assert "messages.modify" in gmail.calls
    assert private in gmail.mail_table[mail].labels
