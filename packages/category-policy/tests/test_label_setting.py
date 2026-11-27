"""Names of the "Other" and archive labels, and the label of a list name (AC 1, 13, 32; ADR-0060)."""

import category_policy
from category_policy import (
    ARCHIVE_LABEL_DEFAULT,
    LABEL_MAX,
    OTHER_LABEL_DEFAULT,
    Category,
    Problem,
    label_for,
    validate_label_setting_name,
)

CATEGORIES = [Category("Aankopen/Marktplaats", "x"), Category("Invoices", "x")]


def _rules(
    name: str,
    counterpart: str = "Archive",
    categories: list[Category] | None = None,
    own_default: str = "Other",
) -> list[str]:
    return [
        p.rule
        for p in validate_label_setting_name(
            name, CATEGORIES if categories is None else categories, counterpart, own_default
        )
    ]


def test_given_a_nested_list_name_when_mapped_then_the_label_is_the_name_without_a_prefix():
    assert label_for("Aankopen/Marktplaats") == "Aankopen/Marktplaats"
    assert label_for("  Huis / Energie ") == "Huis/Energie"
    assert "Assistant" not in label_for("Aankopen/Marktplaats")


def test_given_the_defaults_when_read_then_they_have_no_prefix_and_are_valid():
    assert (OTHER_LABEL_DEFAULT, ARCHIVE_LABEL_DEFAULT) == ("Other", "Archive")
    assert _rules(OTHER_LABEL_DEFAULT, ARCHIVE_LABEL_DEFAULT) == []
    assert _rules(ARCHIVE_LABEL_DEFAULT, OTHER_LABEL_DEFAULT, own_default=ARCHIVE_LABEL_DEFAULT) == []


def test_given_255_and_256_characters_when_validated_then_the_limit_counts_characters_not_bytes():
    assert LABEL_MAX == 255
    assert _rules("a" * 255) == []
    assert _rules("a" * 256) == ["setting_name_too_long"]
    assert _rules("é" * 255) == []
    assert _rules("é" * 256) == ["setting_name_too_long"]
    assert len(("é" * 255).encode()) > LABEL_MAX


def test_given_slash_mistakes_when_validated_then_they_are_invalid():
    for name in (
        "/Bewaard",
        "Bewaard/",
        "Bewaard//2024",
        "Bewaard∕2024",
        "a/ /b",
        "",
        " Bewaard",
        "Bew..aard",
        "Bew\u200baard",
    ):
        assert _rules(name) == ["setting_name_invalid"], name


def test_given_nested_names_when_validated_then_a_clean_nested_name_is_valid():
    assert _rules("Bewaard/2026") == []


def test_given_system_labels_when_validated_then_they_are_refused_in_any_case():
    for name in ("inbox", "INBOX", "SpAm", "TRASH", "CATEGORY_PERSONAL", "category_social", "ＩＮＢＯＸ"):
        assert _rules(name) == ["setting_name_system_label"], name
    assert _rules("Category") == []
    assert _rules("INBOX/Old") == []


def test_given_the_name_of_the_other_setting_when_validated_then_it_is_refused_case_insensitively():
    assert _rules("other", counterpart="Other") == ["setting_name_reserved"]
    assert _rules("ARCHIVE", counterpart="archive") == ["setting_name_reserved"]
    assert _rules("Other", counterpart="Archive") == []


def test_given_a_list_category_when_the_name_equals_or_lies_below_it_then_it_is_refused():
    for name in ("Invoices", "INVOICES", "invoices/Old", "Aankopen/Marktplaats/Oud", "ＩＮＶＯＩＣＥＳ"):
        assert _rules(name) == ["setting_name_category_clash"], name
    assert _rules("Aankopen") == []
    assert _rules("Invoices 2") == []


def test_given_a_refusal_when_returned_then_it_is_one_problem_for_the_setting_field():
    assert validate_label_setting_name("INBOX", [], "Other", "Archive") == [
        Problem("setting_name_system_label", "setting_name")
    ]


def test_given_a_lone_surrogate_when_validated_then_it_does_not_raise():
    assert _rules("a\ud800b") == []


def test_given_the_package_when_searched_then_the_prefix_and_old_archive_helpers_are_gone():
    for gone in ("LABEL_PREFIX", "validate_archive_label", "validate_archive_name"):
        assert not hasattr(category_policy, gone)
        assert gone not in category_policy.__all__


def test_given_the_reserved_names_when_a_setting_is_named_so_then_only_its_own_default_is_allowed():
    assert _rules("Other", counterpart="Bewaard", own_default="Other") == []
    assert _rules("Archive", counterpart="Overig", own_default="Archive") == []
    assert _rules("Archive", counterpart="Bewaard", own_default="Other") == ["setting_name_reserved"]
    assert _rules("other", counterpart="Overig", own_default="Archive") == ["setting_name_reserved"]
    assert _rules("ARCHIVE/Old", counterpart="Other", own_default="Other") == ["setting_name_reserved"]
    assert _rules("Archive/Old", counterpart="Other", own_default="Archive") == ["setting_name_reserved"]
    assert _rules("Other/Mail", counterpart="Archive", own_default="Other") == ["setting_name_reserved"]
    assert _rules("INBOX", counterpart="Archive", own_default="Other") == ["setting_name_system_label"]
