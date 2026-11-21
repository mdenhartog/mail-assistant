"""Direct boundary tests for the v2 rules (AC-1, AC-2, AC-6); the table lives in the contract file."""

from dataclasses import FrozenInstanceError

import pytest

from category_policy import (
    DESCRIPTION_MAX,
    INSTRUCTIONS_MAX,
    LABEL_MAX,
    MAX_CATEGORIES,
    SEGMENT_MAX,
    Category,
    Kind,
    Problem,
    label_for,
    normalise_name,
    validate_category,
    validate_instructions,
    validate_list,
)


def _rules(
    name: str,
    description: str = "x",
    existing: list[str] | None = None,
    labels: list[str] | None = None,
    adoptable: list[str] | None = None,
):
    return [p.rule for p in validate_category(name, description, existing or [], labels or [], adoptable or [])]


def test_given_the_limits_when_read_then_they_match_the_spec():
    assert (SEGMENT_MAX, LABEL_MAX, DESCRIPTION_MAX, INSTRUCTIONS_MAX, MAX_CATEGORIES) == (40, 225, 1500, 4000, 100)


def test_given_huis_energie_when_validated_then_it_is_accepted_and_the_label_is_nested():
    assert _rules("Huis/Energie") == []
    assert label_for("Huis/Energie") == "Assistant/Huis/Energie"


def test_given_the_kinds_when_read_then_they_are_topic_and_extra():
    assert [kind.value for kind in Kind] == ["topic", "extra"]
    assert Category("A", "x").kind is Kind.TOPIC
    assert Category("A", "x", Kind.EXTRA).kind is Kind.EXTRA


def test_given_segments_beyond_the_bmp_when_measured_then_code_points_count_not_bytes():
    assert _rules("\U0001f600" * 40) == []
    assert _rules("\U0001f600" * 41) == ["name_segment_too_long"]


def test_given_surrounding_spaces_when_the_length_is_measured_then_they_do_not_count():
    assert _rules(" " + "a" * 40 + " ") == []
    assert _rules("Huis / " + "a" * 40) == []


def test_given_a_label_of_225_and_226_characters_when_validated_then_only_226_is_refused():
    name_225 = "/".join(["a" * 40] * 5 + ["a" * 10])
    assert len(label_for(name_225)) == LABEL_MAX
    assert _rules(name_225) == []
    assert _rules(name_225 + "a") == ["name_label_too_long"]


def test_given_a_description_with_surrounding_spaces_when_measured_then_they_do_not_count():
    assert _rules("A", " " + "d" * DESCRIPTION_MAX + " ") == []


def test_given_instructions_when_measured_then_4000_pass_and_one_more_is_refused():
    assert validate_instructions("i" * INSTRUCTIONS_MAX) == []
    assert validate_instructions("i" * (INSTRUCTIONS_MAX + 1)) == [Problem("instructions_too_long", "instructions")]


def test_given_a_lone_surrogate_when_validated_then_it_does_not_raise():
    assert _rules("a\ud800b") is not None


def test_given_a_problem_when_built_then_it_is_a_value_with_field_and_index():
    problems = validate_list([Category("A//B", "x")], [], [])

    assert problems == [Problem("name_segment_empty", "name", 0)]


def test_given_the_cap_when_exceeded_then_one_list_problem_without_index_is_added():
    categories = [Category(f"C{i}", "x") for i in range(MAX_CATEGORIES + 1)]

    assert validate_list(categories, [], []) == [Problem("list_too_many", "list", None)]


def test_given_an_ambiguous_case_fold_when_normalised_then_the_key_is_stable():
    assert normalise_name("ẞ") == normalise_name(normalise_name("ẞ")) == "ss"


def test_given_a_label_that_is_an_older_category_when_validated_then_the_name_adopts_it():
    assert _rules("Invoices", labels=["Assistant/Invoices"], adoptable=["Assistant/Invoices"]) == []


def test_given_a_label_that_is_not_adoptable_when_validated_then_the_name_is_refused():
    assert _rules("Invoices", labels=["Assistant/Invoices"], adoptable=["Assistant/Other"]) == ["name_label_exists"]


def test_given_a_category_or_a_problem_when_changed_then_it_is_frozen_and_has_no_instance_dict():
    category = Category("A", "x")
    problem = Problem("name_empty", "name")
    for value in (category, problem):
        assert not hasattr(value, "__dict__")
        with pytest.raises(FrozenInstanceError):
            value.__setattr__("rule" if value is problem else "name", "z")
