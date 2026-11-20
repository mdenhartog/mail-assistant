"""Property-based tests on random Unicode (criterion 8)."""

from hypothesis import given
from hypothesis import strategies as st

from category_policy import RULES, normalise_name, validate_category

TEXT = st.text(max_size=80)


@given(name=TEXT, description=TEXT)
def test_given_any_unicode_when_validated_then_it_never_raises_and_returns_known_rules(name: str, description: str):
    problems = validate_category(name, description, [], [], [])

    assert {p.rule for p in problems} <= set(RULES)


@given(name=TEXT)
def test_given_any_name_when_normalised_twice_then_the_result_is_stable(name: str):
    once = normalise_name(name)

    assert normalise_name(once) == once


@given(name=TEXT, padding=st.sampled_from(["", " ", "\t", "  "]))
def test_given_equal_normalised_names_when_one_is_on_the_list_then_the_other_collides(name: str, padding: str):
    variant = padding + name.upper() + padding
    if normalise_name(variant) != normalise_name(name):
        return

    rules = [p.rule for p in validate_category(variant, "x", [name], [], [])]

    assert "name_duplicate" in rules or "name_empty" in rules
