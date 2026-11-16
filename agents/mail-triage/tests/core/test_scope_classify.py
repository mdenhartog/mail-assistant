"""Which mail a plan may touch, by label names (AC-10, AC-52): every branch of classify (mutation gate)."""

from __future__ import annotations

import pytest

from app.core.scope import Scope, assistant_labels, classify, is_archive_label


@pytest.mark.parametrize("name", ["Archive", "ARCHIVE", "archive"])
def test_given_the_archive_label_in_any_case_then_it_is_the_archive_label(name: str) -> None:
    assert is_archive_label(name) is True


@pytest.mark.parametrize("name", ["Archive/Sub", "Aaa", "Zzz", "", "Archiv"])
def test_given_another_name_then_it_is_not_the_archive_label(name: str) -> None:
    assert is_archive_label(name) is False


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
    assert classify(names) is Scope.OUT


@pytest.mark.parametrize(
    "names",
    [["INBOX"], ["Assistant/A"], ["INBOX", "Assistant/A"], ["Assistant/A", "Other"], ["INBOX", "Archive/Sub"]],
)
def test_given_the_inbox_or_one_assistant_label_then_the_mail_is_in_scope(names: list[str]) -> None:
    assert classify(names) is Scope.IN_SCOPE


@pytest.mark.parametrize(
    "names",
    [
        ["Assistant/A", "Assistant/B"],
        ["INBOX", "Assistant/A", "Assistant/B"],
        ["Assistant/A", "Assistant/B", "Assistant/C"],
    ],
)
def test_given_two_or_more_assistant_labels_then_the_mail_is_unclear(names: list[str]) -> None:
    assert classify(names) is Scope.UNCLEAR


def test_given_labels_as_an_iterator_then_they_are_classified_once() -> None:
    assert classify(iter(["INBOX", "Assistant/A"])) is Scope.IN_SCOPE
