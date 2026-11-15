"""U-mail-categories-14, criterion 1: which mail can become a plan item (AC-10, AC-52)."""

from __future__ import annotations

import pytest

from app.core.scope import Scope, assistant_labels, classify

MATRIX = [
    pytest.param({"INBOX"}, Scope.IN_SCOPE, id="inbox"),
    pytest.param({"Assistant/Finance"}, Scope.IN_SCOPE, id="label-only"),
    pytest.param({"INBOX", "Assistant/Finance"}, Scope.IN_SCOPE, id="inbox-and-label"),
    pytest.param({"Assistant/Old shop"}, Scope.IN_SCOPE, id="legacy-label"),
    pytest.param({"Archive"}, Scope.OUT, id="archive"),
    pytest.param({"Archive", "Assistant/Finance"}, Scope.OUT, id="archive-with-label"),
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


@pytest.mark.parametrize(("labels", "expected"), MATRIX)
def test_only_mail_in_scope_can_become_an_item(labels: set[str], expected: Scope) -> None:
    assert classify(labels) is expected


def test_the_label_name_is_matched_exactly_not_by_prefix_look_alike() -> None:
    assert classify({"assistant/Finance"}) is Scope.OUT
    assert classify({"Assistant"}) is Scope.OUT
    assert assistant_labels({"INBOX", "Assistant/Finance", "Assistantx/Y"}) == ["Assistant/Finance"]
