"""U-label-structure-12: the comparison of a file with the stored list, without a database."""

import uuid

import pytest

from app.categories_models import CategoryProblem
from app.categories_repo import StoredCategory, StoredList
from app.services.category_upload import FileRefused, parse_file, plan_of, policy_problems
from category_policy import Kind
from category_policy.yaml_file import FILE_RULE_TEXT

INVOICES = uuid.UUID(int=11)
OLD = uuid.UUID(int=12)
NEW = uuid.UUID(int=99)


def stored(*, labels: tuple[str, ...] = ()) -> StoredList:
    categories = (
        StoredCategory(INVOICES, "Invoices", "Bills", Kind.TOPIC, notify=False, senders=()),
        StoredCategory(OLD, "Old", "Gone soon", Kind.TOPIC, notify=False, senders=()),
    )
    return StoredList(1, categories, "", "Assistant/Archive", {}, {}, labels)


def file_of(*categories: tuple[str, str]) -> bytes:
    body = "".join(f"  - name: {name}\n    description: {description}\n" for name, description in categories)
    return f"schema: 1\ncategories:\n{body}".encode()


def test_given_equal_names_by_case_and_width_when_planned_then_they_keep_their_id_and_count_as_changed_or_same() -> (
    None
):
    parsed = parse_file(file_of(("invoices", "Bills"), ("Fresh", "d")))

    plan = plan_of(parsed, stored(), lambda: NEW)

    assert [row.id for row in plan.rows] == [INVOICES, NEW]
    assert (plan.added, plan.changed, plan.removed) == (1, 1, ["Old"])  # "invoices" differs from "Invoices" as text
    assert plan.new_ids == {NEW}


def test_given_the_same_list_when_planned_then_nothing_is_added_changed_or_removed() -> None:
    parsed = parse_file(file_of(("Invoices", "Bills"), ("Old", "Gone soon")))

    plan = plan_of(parsed, stored(), lambda: NEW)

    assert (plan.added, plan.changed, plan.removed, plan.new_ids) == (0, 0, [], frozenset())


def test_given_a_name_whose_label_is_an_older_category_when_planned_then_it_is_adopted_not_refused() -> None:
    parsed = parse_file(file_of(("Trips", "d")))

    plan = plan_of(parsed, stored(labels=("Assistant/Trips",)), lambda: NEW)

    assert [row.id for row in plan.rows] == [NEW]


def test_given_a_problem_against_the_stored_list_when_reported_then_it_names_field_and_line_but_no_value() -> None:
    found = [CategoryProblem(rule="name_label_exists", field="name", index=2, position=None, other_index=None)]

    problems = policy_problems(found)

    assert [(p.rule, p.line, p.field) for p in problems] == [("name_label_exists", 1, "categories[2].name")]
    assert problems[0].message == FILE_RULE_TEXT["name_label_exists"]


def test_given_a_hostile_file_when_parsed_then_every_problem_has_a_line_a_field_and_a_fixed_text() -> None:
    with pytest.raises(FileRefused) as refused:
        parse_file(b"schema: 1\ncategories:\n  - &a\n    name: canary-name-12\n    description: d\n    extra: x\n")

    problems = refused.value.problems
    assert {p.rule for p in problems} >= {"anchor"}
    assert all(p.line >= 1 and p.field and p.message for p in problems)
    assert "canary" not in repr(problems)
