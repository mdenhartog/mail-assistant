"""U-label-prefix-removal-04, criterion 6 (AC 11, ADR-0060): the Gmail methods the agent may call, by reflection.

The allow-list lives in this test on purpose: a new Gmail call in an adapter fails here until a person changes the
list, with the ADR in hand. Exactly one delete is reserved, ``labels.delete`` by id; unit 07 implements it. There is
no trash, no delete of mail and no send in the label and mail adapters.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.adapters import gmail_read
from app.adapters.gmail_resort import GmailResort
from app.core.managed import ManagedLabel, ManagedSet, Role
from tests.fakes.fake_gmail import FakeGmail

ALLOWED_CALLS = {
    "labels.list",
    "labels.get",
    "labels.create",
    "labels.patch",
    "messages.list",
    "messages.get",
    "messages.modify",
    "history.list",
    "getProfile",
}
RESERVED_DELETE = "labels.delete"  # by id, one place only; unit 07 adds the use case and its adapter method
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
ADAPTERS = Path(inspect.getsourcefile(gmail_read) or "").parent
# gmail_apply is read as text: importing it needs the re-sort use case, which unit 18 repairs.
SOURCES = {
    name: (ADAPTERS / f"{name}.py").read_text(encoding="utf-8")
    for name in ("gmail_read", "gmail_resort", "gmail_apply")
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
