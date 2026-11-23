"""Direct tests for the archive label rules (AC-42, C-11, ADR-0059); the table lives in the contract file."""

from category_policy import (
    ARCHIVE_LABEL_DEFAULT,
    Category,
    Problem,
    validate_archive_label,
    validate_archive_name,
)


def test_given_the_default_archive_label_when_validated_then_it_is_accepted_next_to_any_categories():
    categories = [Category("Invoices", "x"), Category("Huis/Energie", "x")]

    assert ARCHIVE_LABEL_DEFAULT == "Assistant/Archive"
    assert validate_archive_label(ARCHIVE_LABEL_DEFAULT, categories) == []


def test_given_a_refused_name_when_validated_then_the_problem_names_the_archive_label_field():
    assert validate_archive_label("INBOX", []) == [Problem("archive_system_label", "archive_label")]


def test_given_a_lone_surrogate_when_validated_then_it_does_not_raise():
    assert validate_archive_label("a\ud800b", []) == []


def test_given_only_a_name_when_validated_then_the_name_rules_apply_without_categories():
    assert validate_archive_name(ARCHIVE_LABEL_DEFAULT) == []
    assert validate_archive_name("Bewaard/2026") == []
    assert validate_archive_name("INBOX") == [Problem("archive_system_label", "archive_label")]
    assert validate_archive_name("ＩＮＢＯＸ") == [Problem("archive_system_label", "archive_label")]
    assert validate_archive_name("Archive∕Old") == [Problem("archive_invalid", "archive_label")]
    assert validate_archive_name("Assistant/Invoices") == [Problem("archive_inside_assistant", "archive_label")]
    assert validate_archive_name("") == [Problem("archive_invalid", "archive_label")]


def test_given_a_name_when_validated_by_name_only_then_it_equals_the_check_with_no_categories():
    for name in ("Archive", "x/y", "Assistant/Archive", "Assistant/Other", "Trash", "a..b", " a"):
        assert validate_archive_name(name) == validate_archive_label(name, [])
