"""Which mail a plan may touch, by label names (AC-10, AC-52): every branch of classify (mutation gate)."""

from __future__ import annotations

import pytest

from app.core.scope import ArchiveLabel, Scope, assistant_labels, classify, is_archive_label

ARCHIVE = "Archive"


@pytest.mark.parametrize("name", ["Archive", "ARCHIVE", "archive"])
def test_given_the_archive_label_in_any_case_then_it_is_the_archive_label(name: str) -> None:
    assert is_archive_label(name, ARCHIVE) is True


@pytest.mark.parametrize("name", ["Archive/Sub", "Aaa", "Zzz", "", "Archiv"])
def test_given_another_name_then_it_is_not_the_archive_label(name: str) -> None:
    assert is_archive_label(name, ARCHIVE) is False


def test_given_labels_when_the_assistant_ones_are_taken_then_they_are_sorted_and_the_prefix_is_exact() -> None:
    names = ["Assistant/B", "INBOX", "assistant/x", "Assistant/A", "XAssistant/Y"]
    assert assistant_labels(names) == ["Assistant/A", "Assistant/B"]
    assert assistant_labels(iter(["Assistant/Z"])) == ["Assistant/Z"]


@pytest.mark.parametrize(
    "names",
    [
        ["SPAM"],
        ["TRASH"],
        ["DRAFT"],
        ["INBOX", "SPAM"],
        ["INBOX", "TRASH", "Assistant/A"],
        ["Assistant/A", "DRAFT"],
        ["Archive"],
        ["INBOX", "Archive"],
        ["archive", "Assistant/A"],
        ["Archive", "Assistant/A", "Assistant/B"],
        [],
        ["Other"],
        ["SENT"],
    ],
)
def test_given_excluded_archived_or_unrelated_labels_then_the_mail_is_out(names: list[str]) -> None:
    assert classify(names, ARCHIVE, frozenset()) is Scope.OUT


@pytest.mark.parametrize(
    "names",
    [["INBOX"], ["Assistant/A"], ["INBOX", "Assistant/A"], ["Assistant/A", "Other"], ["INBOX", "Archive/Sub"]],
)
def test_given_the_inbox_or_one_assistant_label_then_the_mail_is_in_scope(names: list[str]) -> None:
    assert classify(names, ARCHIVE, frozenset()) is Scope.IN_SCOPE


@pytest.mark.parametrize(
    "names",
    [
        ["Assistant/A", "Assistant/B"],
        ["INBOX", "Assistant/A", "Assistant/B"],
        ["Assistant/A", "Assistant/B", "Assistant/C"],
    ],
)
def test_given_two_or_more_assistant_labels_then_the_mail_is_unclear(names: list[str]) -> None:
    assert classify(names, ARCHIVE, frozenset()) is Scope.UNCLEAR


def test_given_labels_as_an_iterator_then_they_are_classified_once() -> None:
    assert classify(iter(["INBOX", "Assistant/A"]), ARCHIVE, frozenset()) is Scope.IN_SCOPE


@pytest.mark.parametrize("archive", ["Assistant/Archive", "Bewaard", "Mail/Done"])
def test_given_a_configured_archive_label_then_a_mail_with_it_is_out_of_scope_and_wins_over_a_category(
    archive: str,
) -> None:
    assert is_archive_label(archive.upper(), archive) is True
    assert classify({archive, "INBOX"}, archive, frozenset()) is Scope.OUT
    assert classify({archive, "Assistant/Travel"}, archive, frozenset()) is Scope.OUT


def test_given_a_configured_archive_label_then_the_old_name_is_not_protected_any_more() -> None:
    assert classify({"Archive", "INBOX"}, "Bewaard", frozenset()) is Scope.IN_SCOPE
    assert is_archive_label("Archive", "Bewaard") is False


def test_given_a_renamed_archive_label_then_a_mail_with_it_and_a_category_is_out_of_scope() -> None:
    archive = ArchiveLabel("Bewaard")
    assert classify({"Bewaard", "Assistant/Travel", "INBOX"}, archive.name, frozenset()) is Scope.OUT

    archive.name = "Mail/Done"  # the sync renamed the label by id; the mail now carries the new name

    assert classify({"Mail/Done", "Assistant/Travel", "INBOX"}, archive.name, frozenset()) is Scope.OUT
    assert classify({"Bewaard", "INBOX"}, archive.name, frozenset()) is Scope.IN_SCOPE


@pytest.mark.parametrize("names", [["INBOX", "SENT"], ["Assistant/Work", "SENT"], ["SENT"]])
def test_given_the_users_own_sent_mail_then_it_is_out_of_scope(names: list[str]) -> None:
    assert classify(names, "Archive", ()) is Scope.OUT
