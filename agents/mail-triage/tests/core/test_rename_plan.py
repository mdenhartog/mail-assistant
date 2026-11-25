"""U-label-prefix-removal-06, the pure plan (spec D8, D9, AC 4, 20): which old labels become which new names."""

from __future__ import annotations

from app.core.managed import LabelRef
from app.core.rename_plan import PlanItem, build_plan

OLD = "Assistant" + "/"  # the source tree does not carry the old prefix as a literal elsewhere


def ref(label_id: str, name: str) -> LabelRef:
    return LabelRef(label_id, name)


def test_given_a_prefixed_label_when_planned_then_the_new_name_is_the_old_name_without_the_prefix() -> None:
    plan = build_plan([ref("L1", f"{OLD}Aankopen/Marktplaats")])

    assert plan == [PlanItem("L1", f"{OLD}Aankopen/Marktplaats", "Aankopen/Marktplaats", "rename")]


def test_given_the_prefix_in_another_letter_case_when_planned_then_it_is_still_removed() -> None:
    plan = build_plan([ref("L1", f"{OLD.upper()}Bills"), ref("L2", f"{OLD.lower()}Work")])

    assert {(item.label_id, item.new_name) for item in plan} == {("L1", "Bills"), ("L2", "Work")}


def test_given_labels_outside_the_prefix_when_planned_then_they_are_left_out() -> None:
    labels = [ref("L1", "Bills"), ref("L2", "INBOX"), ref("L3", "Assistantship/Notes"), ref("L4", "Assistant")]

    assert build_plan(labels) == []  # the bare root has no name to give: it is left to the delete rule


def test_given_an_existing_label_with_the_new_name_in_any_case_when_planned_then_the_action_is_merge() -> None:
    plan = build_plan([ref("L1", f"{OLD}Amerika"), ref("L2", "amerika")])

    assert plan == [PlanItem("L1", f"{OLD}Amerika", "Amerika", "merge")]


def test_given_a_new_name_that_is_a_system_label_when_planned_then_the_label_is_not_planned() -> None:
    plan = build_plan([ref("L1", f"{OLD}Inbox"), ref("INBOX", "INBOX"), ref("L2", f"{OLD}Bills")])

    assert [item.label_id for item in plan] == ["L2"]  # mail is never merged onto a system label


def test_given_a_name_that_is_empty_or_still_prefixed_when_planned_then_the_label_is_not_planned() -> None:
    labels = [ref("L1", OLD), ref("L2", f"{OLD}{OLD}Twice"), ref("L3", f"{OLD}Fine")]

    assert [item.label_id for item in build_plan(labels)] == ["L3"]


def test_given_labels_of_categories_that_left_the_list_when_planned_then_they_are_part_of_the_plan() -> None:
    plan = build_plan([ref("L1", f"{OLD}Retired"), ref("L2", f"{OLD}Current")])

    assert [item.new_name for item in plan] == ["Current", "Retired"]  # ordered by name, the plan is stable
