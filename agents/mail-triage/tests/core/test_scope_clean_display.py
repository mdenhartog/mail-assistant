"""clean_display: text for the review page keeps no hidden or line-breaking characters (MC-20, SEC-06)."""

from __future__ import annotations

import pytest

from app.core.scope import clean_display

LINE_SEPARATOR = chr(0x2028)
PARAGRAPH_SEPARATOR = chr(0x2029)
ZERO_WIDTH_SPACE = chr(0x200B)
RIGHT_TO_LEFT_OVERRIDE = chr(0x202E)


@pytest.mark.parametrize("separator", [LINE_SEPARATOR, PARAGRAPH_SEPARATOR], ids=["u2028", "u2029"])
def test_given_a_line_or_paragraph_separator_when_cleaned_then_it_becomes_a_space(separator: str) -> None:
    assert clean_display(f"Pay{separator}now", 50) == "Pay now"


def test_given_format_and_control_characters_when_cleaned_then_they_are_removed_or_spaced() -> None:
    text = f"a{ZERO_WIDTH_SPACE}b{chr(9)}c{RIGHT_TO_LEFT_OVERRIDE}d"

    assert clean_display(text, 50) == "ab cd"
