"""Property-based tests on random Unicode."""

from hypothesis import given
from hypothesis import strategies as st

from category_policy import RULES, label_for, normalise_name, validate_category, validate_instructions

TEXT = st.text(max_size=80)


@given(name=TEXT, description=TEXT)
def test_given_any_unicode_when_validated_then_it_never_raises_and_returns_known_rules(name: str, description: str):
    problems = validate_category(name, description, [], ("Other", "Archive"))

    assert {p.rule for p in problems} <= set(RULES)


@given(text=st.text(max_size=5000))
def test_given_any_instructions_when_validated_then_it_never_raises_and_returns_known_rules(text: str):
    assert {p.rule for p in validate_instructions(text)} <= set(RULES)


@given(name=TEXT)
def test_given_any_name_when_normalised_twice_then_the_result_is_stable(name: str):
    once = normalise_name(name)

    assert normalise_name(once) == once


@given(name=TEXT)
def test_given_any_name_when_labelled_then_the_label_is_stable_and_has_no_prefix(name: str):
    label = label_for(name)

    assert label_for(label) == label
    assert label == "/".join(part.strip() for part in label.split("/"))


@given(name=TEXT, padding=st.sampled_from(["", " ", "\t", "  "]))
def test_given_equal_normalised_names_when_one_is_on_the_list_then_the_other_collides(name: str, padding: str):
    variant = padding + name.upper() + padding
    if normalise_name(variant) != normalise_name(name):
        return

    rules = [p.rule for p in validate_category(variant, "x", [name], ("Other", "Archive"))]

    assert "name_duplicate" in rules or "name_empty" in rules
