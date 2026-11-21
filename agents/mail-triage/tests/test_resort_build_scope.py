"""U-mail-categories-14, criterion 1: which mail can become a plan item (AC-10, AC-52)."""

from __future__ import annotations

import pytest

from app.core.scope import Scope, assistant_labels, classify, is_archive_label

MATRIX = [
    pytest.param({"INBOX"}, Scope.IN_SCOPE, id="inbox"),
    pytest.param({"Assistant/Finance"}, Scope.IN_SCOPE, id="label-only"),
    pytest.param({"INBOX", "Assistant/Finance"}, Scope.IN_SCOPE, id="inbox-and-label"),
    pytest.param({"Assistant/Old shop"}, Scope.IN_SCOPE, id="legacy-label"),
    pytest.param({"Archive"}, Scope.OUT, id="archive"),
    pytest.param({"Archive", "Assistant/Finance"}, Scope.OUT, id="archive-with-label"),
    pytest.param({"archive", "Assistant/Bills"}, Scope.OUT, id="archive-lowercase-with-label"),
    pytest.param({"ARCHIVE", "INBOX"}, Scope.OUT, id="archive-uppercase-with-inbox"),
    pytest.param({"Folder/Archive", "INBOX"}, Scope.IN_SCOPE, id="nested-archive-is-not-the-archive"),
    pytest.param({"SPAM", "Assistant/Finance"}, Scope.OUT, id="spam"),
    pytest.param({"TRASH"}, Scope.OUT, id="trash"),
    pytest.param({"DRAFT", "INBOX"}, Scope.OUT, id="draft"),
    pytest.param({"SENT"}, Scope.OUT, id="sent-only"),
    pytest.param({"Receipts 2019"}, Scope.OUT, id="user-label-only"),
    pytest.param(set(), Scope.OUT, id="no-labels"),
    pytest.param({"Assistant/A", "Assistant/B"}, Scope.UNCLEAR, id="two-labels"),
    pytest.param({"INBOX", "Assistant/A", "Assistant/B"}, Scope.UNCLEAR, id="inbox-two-labels"),
    pytest.param({"TRASH", "Assistant/A", "Assistant/B"}, Scope.OUT, id="trash-wins-over-two-labels"),
]

ARCHIVE = "Archive"


@pytest.mark.parametrize(("labels", "expected"), MATRIX)
def test_only_mail_in_scope_can_become_an_item(labels: set[str], expected: Scope) -> None:
    assert classify(labels, ARCHIVE) is expected


def test_the_label_name_is_matched_exactly_not_by_prefix_look_alike() -> None:
    assert classify({"assistant/Finance"}, ARCHIVE) is Scope.OUT
    assert classify({"Assistant"}, ARCHIVE) is Scope.OUT
    assert assistant_labels({"INBOX", "Assistant/Finance", "Assistantx/Y"}) == ["Assistant/Finance"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Archive", True), ("archive", True), ("ARCHIVE", True), ("Archive/x", False), ("Old/Archive", False)],
)
def test_is_archive_label_is_case_insensitive_and_top_level_only(name: str, expected: bool) -> None:
    assert is_archive_label(name, ARCHIVE) is expected
