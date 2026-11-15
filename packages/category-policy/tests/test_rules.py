"""Direct boundary tests for the rules (AC-2, AC-8); the table lives in the contract file."""

from category_policy import (
    DESCRIPTION_MAX,
    MAX_CATEGORIES,
    NAME_MAX,
    Category,
    Problem,
    normalise_name,
    validate_category,
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
    assert (NAME_MAX, DESCRIPTION_MAX, MAX_CATEGORIES) == (40, 500, 50)


def test_given_a_name_of_code_points_beyond_the_bmp_when_measured_then_code_points_count_not_bytes():
    assert _rules("\U0001f600" * 40) == []
    assert _rules("\U0001f600" * 41) == ["name_too_long"]


def test_given_surrounding_spaces_when_the_length_is_measured_then_they_do_not_count():
    assert _rules(" " + "a" * 40 + " ") == []


def test_given_a_description_with_surrounding_spaces_when_measured_then_they_do_not_count():
    assert _rules("A", " " + "d" * 500 + " ") == []


def test_given_a_lone_surrogate_when_validated_then_it_does_not_raise():
    assert _rules("a\ud800b") is not None


def test_given_a_problem_when_built_then_it_is_a_value_with_field_and_index():
    problems = validate_list([Category("A/B", "x")], [], [])

    assert problems == [Problem("name_slash", "name", 0)]


def test_given_a_duplicate_that_also_matches_a_label_when_validated_then_only_the_duplicate_is_reported():
    assert _rules("Invoices", existing=["invoices"], labels=["Assistant/Invoices"]) == ["name_duplicate"]


def test_given_an_ambiguous_case_fold_when_normalised_then_the_key_is_stable():
    assert normalise_name("ẞ") == normalise_name(normalise_name("ẞ")) == "ss"


def test_given_a_label_that_is_an_older_category_when_validated_then_the_name_adopts_it():
    assert _rules("Invoices", labels=["Assistant/Invoices"], adoptable=["Assistant/Invoices"]) == []


def test_given_a_label_that_is_not_adoptable_when_validated_then_the_name_is_refused():
    assert _rules("Invoices", labels=["Assistant/Invoices"], adoptable=["Assistant/Other"]) == ["name_label_exists"]
