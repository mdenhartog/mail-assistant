"""Tips for the review page: clean the model's text and keep a suggested sender only when it is earned (C-15, AC-52).

A tip is untrusted model output. It is stored and shown as plain text: markup, links, mentions, domain-like words and
lines that read as instructions are removed, and the whole is capped. A sender is never taken from the text: the model
may name one in a separate field, and the code keeps it only when it is the verified (authenticated) domain of at least
``MIN_SENDER_ITEMS`` below-threshold items of the category and is not on a refused list. The code writes the sender and
its count itself. Nothing here applies a tip to the list or to Gmail.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from category_policy import is_refused_domain, normalise_domain

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = ["MIN_SENDER_ITEMS", "TIP_MAX_CHARS", "clean_tip", "compose_tip", "qualified_domains"]

TIP_MAX_CHARS = 500  # the column check of migration 0029
MIN_SENDER_ITEMS = 3  # Claude's call on the number (spec C-15)

_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG = re.compile(r"<[^>]*>")
_ENTITY = re.compile(r"&#?\w+;")
_URL = re.compile(r"\S*://\S*|\bwww\.\S*", re.IGNORECASE)
_MENTION = re.compile(r"@\S*")
_DOMAIN_LIKE = re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}\b")
_MARKS = re.compile(r"[`*<>\[\]]")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_INSTRUCTION = re.compile(
    r"\b(ignore|disregard|forget|override|bypass|pretend)\b"
    r"|\b(system|developer)\s+(prompt|message)\b"
    r"|^\s*(system|assistant|user|developer)\s*:"
    r"|\byou\s+(are|must|should)\s+(now|always|never)\b"
    r"|\b(act|behave)\s+as\b"
    r"|\bnew\s+instructions?\b"
    r"|\b(reveal|print|repeat)\b.*\b(prompt|instructions|rules)\b",
    re.IGNORECASE,
)


def clean_tip(text: str, limit: int = TIP_MAX_CHARS) -> str:
    """The plain text of a tip: no markup, link, mention, domain or instruction-like sentence; cut at ``limit``."""
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _TAG.sub("", text)
    for pattern in (_ENTITY, _URL, _MENTION, _DOMAIN_LIKE):
        text = pattern.sub("", text)
    text = _MARKS.sub("", text)
    sentences = (s.strip() for s in _SENTENCE_END.split(text))
    kept = (" ".join(s.split()) for s in sentences if s.strip() and not _INSTRUCTION.search(s))
    return " ".join(kept)[: max(limit, 0)].rstrip()


def qualified_domains(verified: Iterable[str | None]) -> dict[str, int]:
    """The verified sender domains of at least ``MIN_SENDER_ITEMS`` items that are not refused, with their counts.

    ``verified`` holds one entry per below-threshold item of one category: the domain Gmail vouched for, or ``None``.
    """
    counts = Counter(domain for domain in verified if domain is not None)
    return {d: n for d, n in counts.items() if n >= MIN_SENDER_ITEMS and not is_refused_domain(d)}


def compose_tip(text: str, suggested: str | None, qualified: Mapping[str, int]) -> str | None:
    """The tip to store: cleaned text plus the suggested sender when it qualified; ``None`` when no text is left."""
    domain = None if suggested is None else normalise_domain(suggested.strip())
    suffix = ""
    if domain is not None and domain in qualified:
        suffix = f" Suggested sender: {domain} ({qualified[domain]} items)."
    cleaned = clean_tip(text, TIP_MAX_CHARS - len(suffix))
    return f"{cleaned}{suffix}" if cleaned else None
