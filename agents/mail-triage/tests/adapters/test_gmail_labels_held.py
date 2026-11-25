"""RED-002: while the rename plan is not done the adapter works on stored ids only (R4, ADR-0061 point 1).

The managed set carries the hold (``writes_held``); the one guard is in ``ManagedLabels``. With the hold on, a label
is never created, adopted by name or renamed: not even a label that already exists under the wanted name is taken.
"""

from __future__ import annotations

import pytest

from app.adapters.gmail_read import GmailReader, LabelRefused
from app.adapters.gmail_resort import GmailResort
from app.core.mail_errors import LabelWritesHeld
from app.core.managed import ManagedLabel, ManagedSet, Role
from tests.fakes.fake_gmail import FakeGmail

_WRITES = {"labels.create", "labels.patch", "labels.delete", "messages.modify"}


def held(*labels: ManagedLabel) -> ManagedSet:
    return ManagedSet(labels, writes_held=True)


def other(label_id: str | None = None) -> ManagedLabel:
    return ManagedLabel("Other", label_id, Role.OTHER)


def writes(gmail: FakeGmail) -> list[str]:
    return [call for call in gmail.calls if call in _WRITES]


def test_given_a_held_set_when_a_label_without_an_id_is_ensured_then_none_is_created() -> None:
    gmail = FakeGmail()
    adapter = GmailResort(gmail, held(other()), sleep=lambda _s: None)
    before = dict(gmail.label_table)

    with pytest.raises(LabelWritesHeld):
        adapter.ensure_label(other())

    assert gmail.label_table == before
    assert writes(gmail) == []


def test_given_a_held_set_when_a_label_of_that_name_exists_then_it_is_not_adopted() -> None:
    gmail = FakeGmail()
    existing = gmail.add_label("Other")  # a label of the user: the plan must see it as a clash, not the agent adopt it
    adapter = GmailResort(gmail, held(other()), sleep=lambda _s: None)

    with pytest.raises(LabelWritesHeld):
        adapter.ensure_label(other())

    assert gmail.label_table[existing] == "Other"
    assert writes(gmail) == []


def test_given_a_held_set_when_the_stored_id_exists_then_it_is_used_without_a_write() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Assistant/Other")
    adapter = GmailResort(gmail, held(other(old)), sleep=lambda _s: None)

    assert adapter.ensure_label(other(old)).id == old
    assert gmail.label_table[old] == "Assistant/Other"  # the name is not touched either
    assert writes(gmail) == []


def test_given_a_held_set_when_the_stored_id_is_gone_then_no_label_is_made() -> None:
    gmail = FakeGmail()
    adapter = GmailResort(gmail, held(other("Label_gone")), sleep=lambda _s: None)

    with pytest.raises(LabelWritesHeld):
        adapter.ensure_label(other("Label_gone"))

    assert writes(gmail) == []


def test_given_a_held_set_when_a_label_is_created_or_renamed_then_it_is_refused() -> None:
    gmail = FakeGmail()
    old = gmail.add_label("Assistant/Other")
    adapter = GmailResort(gmail, held(other(old)), sleep=lambda _s: None)

    with pytest.raises(LabelWritesHeld):
        adapter.create_label(other(old))
    with pytest.raises(LabelWritesHeld):
        adapter.rename_label(old, "Other")

    assert gmail.label_table[old] == "Assistant/Other"
    assert writes(gmail) == []


def test_given_a_held_set_when_the_reader_ensures_a_label_then_it_is_held_too() -> None:
    gmail = FakeGmail()
    reader = GmailReader(gmail, sleep=lambda _s: None)
    reader.set_managed(held(other()))

    with pytest.raises(LabelWritesHeld):
        reader.ensure_label(other())

    assert writes(gmail) == []


def test_given_the_hold_is_lifted_when_a_label_is_ensured_then_it_is_made() -> None:
    gmail = FakeGmail()
    adapter = GmailResort(gmail, ManagedSet([other()]), sleep=lambda _s: None)

    made = adapter.ensure_label(other())

    assert gmail.label_table[made.id] == "Other"


def test_a_held_refusal_is_not_a_label_refusal() -> None:
    """Triage turns a refused label into "file under Other"; a hold must not take that road."""
    assert not issubclass(LabelWritesHeld, LabelRefused)
