"""U-label-prefix-removal-03: the managed set is decided by label id, with the name only as a fallback (ADR-0060)."""

from __future__ import annotations

from app.core.managed import LabelRef, ManagedLabel, ManagedSet, Role

FINANCE = ManagedLabel("Finance", "Label_1", Role.TOPIC)


def test_given_a_label_with_a_managed_id_then_it_is_managed() -> None:
    assert ManagedSet([FINANCE]).find(LabelRef("Label_1", "Finance")) == FINANCE


def test_given_a_hand_renamed_label_with_a_stored_id_then_it_is_found_by_id() -> None:
    assert ManagedSet([FINANCE]).find(LabelRef("Label_1", "Money stuff")) == FINANCE


def test_given_a_stored_id_then_a_label_with_the_same_name_and_another_id_is_not_managed() -> None:
    assert ManagedSet([FINANCE]).find(LabelRef("Label_9", "Finance")) is None


def test_given_no_id_known_yet_then_the_name_is_the_fallback_in_any_case() -> None:
    unknown = ManagedLabel("Finance", None, Role.TOPIC)
    assert ManagedSet([unknown]).find(LabelRef("Label_7", "finance")) == unknown


def test_given_a_label_that_is_not_listed_then_it_is_not_managed() -> None:
    assert ManagedSet([FINANCE]).find(LabelRef("Label_5", "Amerika")) is None


def test_given_a_role_then_the_set_answers_by_role() -> None:
    archive = ManagedLabel("Archive", "Label_3", Role.ARCHIVE)
    managed = ManagedSet([FINANCE, archive])
    assert managed.archive == archive
    assert ManagedSet([FINANCE]).archive is None


def test_given_a_managed_set_when_its_labels_are_listed_then_those_with_and_without_an_id_are_both_there() -> None:
    with_id = ManagedLabel("Bills", "L1", Role.TOPIC)
    without = ManagedLabel("Travel", None, Role.TOPIC)

    assert set(ManagedSet([with_id, without]).labels()) == {with_id, without}
