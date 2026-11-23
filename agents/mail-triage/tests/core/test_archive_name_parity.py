"""REV-003 / RED-R2-006: the agent and the shared policy give one answer on an archive label name (ADR-0059)."""
# ruff: noqa: RUF001  # the look-alike characters are the subject of these tests

from __future__ import annotations

import pytest

from app.core.scope import usable_archive_name
from category_policy import Category, validate_archive_label

NAMES = [
    ("Archive∕Old", False),  # DIVISION SLASH
    ("Archive／Old", False),  # FULLWIDTH SOLIDUS
    ("ＩＮＢＯＸ", False),  # full-width INBOX
    ("INBOX", False),
    ("Assistant/Archive", True),
    ("Assistant/Invoices", False),
    ("Archive", True),
    ("", False),
    ("Bewaard/2026", True),
    ("Category_x", False),
]


@pytest.mark.parametrize(("name", "usable"), NAMES)
def test_given_an_archive_name_when_both_checks_run_then_they_agree(name: str, usable: bool) -> None:
    assert usable_archive_name(name) is usable
    assert (validate_archive_label(name, []) == []) is usable
    assert (validate_archive_label(name, [Category("Unrelated", "x")]) == []) is usable
