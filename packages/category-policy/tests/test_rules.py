"""Direct boundary tests for the v2 rules (AC-1, AC-2, AC-6); the table lives in the contract file."""

import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import category_policy
from category_policy import (
    DESCRIPTION_MAX,
    INSTRUCTIONS_MAX,
    LABEL_MAX,
    MAX_CATEGORIES,
    RULES,
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
    settings: tuple[str, str] = ("Other", "Archive"),
):
    return [p.rule for p in validate_category(name, description, existing or [], settings)]


def test_given_the_limits_when_read_then_they_match_the_spec():
    assert (SEGMENT_MAX, LABEL_MAX, DESCRIPTION_MAX, INSTRUCTIONS_MAX, MAX_CATEGORIES) == (40, 255, 1500, 4000, 100)


def test_given_huis_energie_when_validated_then_it_is_accepted_and_the_label_is_nested():
    assert _rules("Huis/Energie") == []
    assert label_for("Huis/Energie") == "Huis/Energie"


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


def test_given_a_label_of_255_and_256_characters_when_validated_then_only_226_is_refused():
    name_255 = "/".join(["a" * 40] * 6 + ["a" * 9])
    assert len(label_for(name_255)) == LABEL_MAX
    assert _rules(name_255) == []
    assert _rules(name_255 + "a") == ["name_label_too_long"]


def test_given_a_description_with_surrounding_spaces_when_measured_then_they_do_not_count():
    assert _rules("A", " " + "d" * DESCRIPTION_MAX + " ") == []


def test_given_instructions_when_measured_then_4000_pass_and_one_more_is_refused():
    assert validate_instructions("i" * INSTRUCTIONS_MAX) == []
    assert validate_instructions("i" * (INSTRUCTIONS_MAX + 1)) == [Problem("instructions_too_long", "instructions")]


def test_given_a_lone_surrogate_when_validated_then_it_does_not_raise():
    assert _rules("a\ud800b") is not None


def test_given_a_problem_when_built_then_it_is_a_value_with_field_and_index():
    problems = validate_list([Category("A//B", "x")], ("Other", "Archive"))

    assert problems == [Problem("name_segment_empty", "name", 0)]


def test_given_the_cap_when_exceeded_then_one_list_problem_without_index_is_added():
    categories = [Category(f"C{i}", "x") for i in range(MAX_CATEGORIES + 1)]

    assert validate_list(categories, ("Other", "Archive")) == [Problem("list_too_many", "list", None)]


def test_given_an_ambiguous_case_fold_when_normalised_then_the_key_is_stable():
    assert normalise_name("ẞ") == normalise_name(normalise_name("ẞ")) == "ss"


def test_given_a_category_named_like_an_existing_label_when_the_list_is_validated_then_it_is_accepted():
    # AC 19: the package no longer knows which labels exist; an existing label is adopted, never refused.
    assert list(inspect.signature(validate_list).parameters) == ["categories", "settings"]
    assert list(inspect.signature(validate_category).parameters) == ["name", "description", "existing", "settings"]
    assert validate_list([Category("Invoices", "x"), Category("Huis/Energie", "x")], ("Other", "Archive")) == []


def test_given_the_same_list_when_validated_twice_then_the_result_is_identical():
    categories = [Category("Invoices", "x"), Category("Archive", "x"), Category("invoices", "")]

    assert validate_list(categories, ("Other", "Archive")) == validate_list(categories, ("Other", "Archive"))


def test_given_the_package_when_searched_then_adoptable_and_name_label_exists_are_gone():
    assert "name_label_exists" not in RULES
    assert not hasattr(category_policy, "adoptable")
    source = (Path(category_policy.__file__).parent / "policy.py").read_text("utf-8")
    assert "adoptable" not in source
    assert "name_label_exists" not in source


@pytest.mark.parametrize("name", ["Archive", "Other", "archive/Taxes", "OTHER", "ＯＴＨＥＲ", "Other/Things"])
def test_given_a_reserved_name_when_validated_as_a_category_then_it_is_refused_in_any_case(name: str):
    assert _rules(name) == ["name_reserved"]


@pytest.mark.parametrize(
    "name",
    [
        "Inbox",
        "INBOX",
        "spam",
        "Trash",
        "SENT",
        "Draft",
        "STARRED",
        "Unread",
        "important",
        "CHAT",
        "CATEGORY_PERSONAL",
        "category_social",
    ],
)
def test_given_a_gmail_system_label_when_validated_as_a_category_then_it_is_refused_in_any_case(name: str):
    assert _rules(name) == ["name_reserved"]
    assert _rules("INBOX/Old") == []
    assert _rules("Category") == []


def test_given_a_renamed_setting_when_a_category_equals_its_name_then_it_is_refused_as_a_clash():
    settings = ("Overig", "Bewaard/2026")
    assert _rules("overig", settings=settings) == ["name_setting_clash"]
    assert _rules("BEWAARD / 2026", settings=settings) == ["name_setting_clash"]
    assert _rules("Bewaard", settings=settings) == []
    assert _rules("Huis/Overig", settings=settings) == []


def test_given_a_list_when_a_category_clashes_with_a_setting_then_the_problem_carries_its_index():
    problems = validate_list([Category("Invoices", "x"), Category("Overig", "x")], ("Overig", "Archive"))

    assert problems == [Problem("name_setting_clash", "name", 1)]


def test_given_a_category_or_a_problem_when_changed_then_it_is_frozen_and_has_no_instance_dict():
    category = Category("A", "x")
    problem = Problem("name_empty", "name")
    for value in (category, problem):
        assert not hasattr(value, "__dict__")
        with pytest.raises(FrozenInstanceError):
            value.__setattr__("rule" if value is problem else "name", "z")
