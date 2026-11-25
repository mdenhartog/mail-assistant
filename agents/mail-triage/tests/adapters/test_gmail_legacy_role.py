"""U-label-prefix-removal-06: the narrow guard for the labels of the rename plan (ADR-0061)."""

from __future__ import annotations

import inspect

import pytest

from app.adapters.gmail_resort import GmailResort, LabelRefused
from app.core.managed import ManagedLabel, ManagedSet, Role
from app.usecases import label_rename
from tests.fakes.fake_gmail import FakeGmail


def adapter_for(gmail: FakeGmail, *labels: ManagedLabel) -> GmailResort:
    return GmailResort(gmail, ManagedSet(labels), sleep=lambda _s: None)


def test_given_a_plan_label_when_renamed_to_a_reserved_list_name_then_the_rename_is_allowed() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Old/Other")
    adapter = adapter_for(gmail, ManagedLabel("Old/Other", old, Role.LEGACY))

    adapter.rename_label(old, "Other")  # the old "Other" label must be able to lose its prefix

    assert gmail.label_table[old] == "Other"


@pytest.mark.parametrize("name", ["INBOX", "Inbox", "CATEGORY_PERSONAL", "a//b", ""])
def test_given_a_plan_label_when_renamed_to_a_system_or_invalid_name_then_it_is_refused(name: str) -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Old/X")
    adapter = adapter_for(gmail, ManagedLabel("Old/X", old, Role.LEGACY))

    with pytest.raises(LabelRefused):
        adapter.rename_label(old, name)

    assert gmail.label_table[old] == "Old/X"


def test_given_a_label_outside_the_plan_item_when_changed_then_the_adapter_refuses() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Old/X")
    other = gmail.add_label("Private")
    mail = gmail.add_mail(labels=("INBOX", other))
    adapter = adapter_for(gmail, ManagedLabel("Old/X", old, Role.LEGACY))

    with pytest.raises(LabelRefused):
        adapter.rename_label(other, "Hijacked")
    with pytest.raises(LabelRefused):
        adapter.add_label(mail, other)
    with pytest.raises(LabelRefused):
        adapter.remove_label(mail, other)


def test_given_the_rename_use_case_when_its_source_is_read_then_it_calls_no_gmail_resource_itself() -> None:
    source = inspect.getsource(label_rename)

    assert ".users()" not in source  # every Gmail call goes through the adapter and its allow-list
