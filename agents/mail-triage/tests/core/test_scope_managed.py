"""U-label-prefix-removal-03, criteria 1 to 5 (AC 2, 3, 15): scope by managed label id and the inbox (ADR-0060)."""

from __future__ import annotations

import pytest

from app.core.managed import LabelRef, ManagedLabel, ManagedSet, Role
from app.core.scope import Scope, classify

TRAVEL = ManagedLabel("Aankopen/Marktplaats", "Label_1", Role.TOPIC)
TOPIC2 = ManagedLabel("Travel", "Label_2", Role.TOPIC)
NEWS = ManagedLabel("Newsletter", "Label_3", Role.EXTRA)
RECEIPT = ManagedLabel("Receipt", "Label_4", Role.EXTRA)
OTHER = ManagedLabel("Other", "Label_5", Role.OTHER)
ARCHIVE = ManagedLabel("Archive", "Label_6", Role.ARCHIVE)
MANAGED = ManagedSet([TRAVEL, TOPIC2, NEWS, RECEIPT, OTHER, ARCHIVE])

INBOX = LabelRef("INBOX", "INBOX")


def ref(label: ManagedLabel) -> LabelRef:
    return LabelRef(label.label_id or "?", label.name)


def test_given_a_managed_label_id_then_the_mail_is_in_scope() -> None:  # criterion 1
    assert classify([ref(TRAVEL)], MANAGED) is Scope.IN_SCOPE


def test_given_only_a_label_that_is_not_managed_then_the_mail_is_out_of_scope() -> None:  # criterion 2
    assert classify([LabelRef("Label_99", "Amerika")], MANAGED) is Scope.OUT


def test_given_an_unmanaged_label_next_to_a_managed_one_then_the_managed_one_decides() -> None:
    assert classify([LabelRef("Label_99", "Amerika"), ref(TRAVEL)], MANAGED) is Scope.IN_SCOPE


def test_given_the_inbox_then_the_mail_is_in_scope() -> None:  # criterion 3
    assert classify([INBOX], MANAGED) is Scope.IN_SCOPE
    assert classify([INBOX, LabelRef("Label_99", "Amerika")], MANAGED) is Scope.IN_SCOPE


def test_given_no_labels_then_the_mail_is_out_of_scope() -> None:
    assert classify([], MANAGED) is Scope.OUT


def test_given_the_archive_and_a_managed_label_then_the_archive_wins() -> None:  # criterion 4
    assert classify([ref(ARCHIVE), ref(TRAVEL)], MANAGED) is Scope.OUT
    assert classify([INBOX, ref(ARCHIVE)], MANAGED) is Scope.OUT


@pytest.mark.parametrize("excluded", ["SPAM", "TRASH", "DRAFT", "SENT"])
def test_given_an_excluded_label_then_it_wins_over_everything(excluded: str) -> None:
    assert classify([INBOX, ref(TRAVEL), LabelRef(excluded, excluded)], MANAGED) is Scope.OUT


def test_given_a_hand_renamed_managed_label_then_it_is_found_by_id() -> None:  # criterion 5
    assert classify([LabelRef("Label_1", "My own name")], MANAGED) is Scope.IN_SCOPE
    assert classify([LabelRef("Label_6", "Kept mail")], MANAGED) is Scope.OUT  # the renamed archive still wins


def test_given_an_archive_without_a_known_id_then_the_name_is_the_fallback_in_any_case() -> None:
    managed = ManagedSet([TRAVEL, ManagedLabel("Archive", None, Role.ARCHIVE)])
    assert classify([LabelRef("Label_8", "ARCHIVE"), ref(TRAVEL)], managed) is Scope.OUT


def test_given_the_other_label_then_the_mail_is_in_scope() -> None:
    assert classify([ref(OTHER)], MANAGED) is Scope.IN_SCOPE


@pytest.mark.parametrize(
    "labels",
    [[TRAVEL, TOPIC2], [NEWS, RECEIPT], [TRAVEL, OTHER], [TRAVEL, TOPIC2, NEWS]],
)
def test_given_two_topics_or_two_extras_then_the_mail_is_unclear(labels: list[ManagedLabel]) -> None:
    assert classify([ref(label) for label in labels], MANAGED) is Scope.UNCLEAR


@pytest.mark.parametrize("labels", [[TRAVEL, NEWS], [NEWS], [OTHER, RECEIPT]])
def test_given_a_topic_next_to_an_extra_then_the_mail_is_in_scope(labels: list[ManagedLabel]) -> None:
    assert classify([ref(label) for label in labels], MANAGED) is Scope.IN_SCOPE
