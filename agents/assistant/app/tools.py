"""The agent's own tools. Add yours here, each with a typed signature, a docstring and a test."""

from __future__ import annotations

from strands import tool

MAX_TEXT = 20_000


@tool
def word_count(text: str) -> int:
    """Count the words in a text (at most 20,000 characters are considered).

    Args:
        text: The text to count the words of.
    """
    return len(text[:MAX_TEXT].split())


LOCAL_TOOLS = [word_count]
