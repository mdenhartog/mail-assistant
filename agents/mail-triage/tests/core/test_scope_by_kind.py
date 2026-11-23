"""U-label-structure-22, criteria 2 and 5: scope is decided by the kind of each label (ADR-0056)."""

from __future__ import annotations

import pytest

from app.core.scope import Scope, classify

ARCHIVE = "Archive"
EXTRAS = frozenset({"Assistant/Newsletter", "Assistant/Receipt"})


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        pytest.param({"INBOX", "Assistant/Finance", "Assistant/Newsletter"}, Scope.IN_SCOPE, id="topic-and-extra"),
        pytest.param({"Assistant/Finance", "Assistant/Receipt"}, Scope.IN_SCOPE, id="topic-and-extra-no-inbox"),
        pytest.param({"Assistant/Newsletter"}, Scope.IN_SCOPE, id="extra-only"),
        pytest.param({"Assistant/Finance", "Assistant/Travel"}, Scope.UNCLEAR, id="two-topics"),
        pytest.param({"Assistant/Finance", "Assistant/Old shop"}, Scope.UNCLEAR, id="topic-and-legacy-label"),
        pytest.param({"Assistant/Newsletter", "Assistant/Receipt"}, Scope.UNCLEAR, id="two-extras"),
        pytest.param({"SPAM", "Assistant/Finance", "Assistant/Newsletter"}, Scope.OUT, id="spam-with-pair"),
        pytest.param({"TRASH", "Assistant/Newsletter"}, Scope.OUT, id="trash-with-extra"),
        pytest.param({"Archive", "Assistant/Finance", "Assistant/Newsletter"}, Scope.OUT, id="archive-with-pair"),
    ],
)
def test_scope_is_decided_by_the_kind_of_each_label(labels: set[str], expected: Scope) -> None:
    assert classify(labels, ARCHIVE, EXTRAS) is expected
