"""Pinned mail: the app's own sign-in mail and Google security mail never leave the inbox (AC-39, MC-19, ADR-0045).

The two kinds are told apart by their own allow-list, because they are treated differently afterwards: Google security
mail raises an alert, the sign-in code mail stays silent (ADR-0048).

The decision rests on Gmail's own verdict, never on the model or on the list. Only the topmost
``Authentication-Results`` header counts, because mail servers add theirs on top and a sender can only forge headers
below it. The header must name ``mx.google.com`` as its server, show ``dmarc=pass`` and a ``header.from`` domain that
is the domain of the From address and is on the configured allow-list.
The header is tokenised as RFC 8601 says (nested comments, quoted strings, escapes) and anything ambiguous fails closed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["GMAIL_AUTHSERV_ID", "PinnedKind", "PinnedSenders", "pinned_kind"]

GMAIL_AUTHSERV_ID = "mx.google.com"
_DMARC_ANYWHERE = re.compile(r"(?<![\w.-])dmarc\s*=", re.IGNORECASE)
_DMARC = re.compile(r"^\s*dmarc\s*=\s*(?P<result>[a-z]+)(?P<rest>.*)$", re.IGNORECASE | re.DOTALL)
_HEADER_FROM = re.compile(r"(?:^|\s)header\.from\s*=\s*(?P<domain>[^\s;]+)", re.IGNORECASE)
_QUOTED = '"_"'  # what a quoted string becomes: its content can never look like a result or a domain


class PinnedKind(StrEnum):
    """Which pinned kind a verified mail is."""

    GOOGLE_SECURITY = "google_security"
    SIGN_IN_CODE = "sign_in_code"


@dataclass(frozen=True, slots=True)
class PinnedSenders:
    """The sender domains of each pinned kind, lower case."""

    google_security: frozenset[str]
    sign_in: frozenset[str]


def _domain_of(address: str) -> str:
    return address.rpartition("@")[2].strip().casefold()


def pinned_kind(auth_results: Sequence[str], sender: str, senders: PinnedSenders) -> PinnedKind | None:
    """The pinned kind of a mail when Gmail vouches (DMARC pass) for a From domain on that kind's list, else ``None``.

    ``auth_results`` holds the ``Authentication-Results`` values in header order, topmost first; ``sender`` is the
    parsed From address.
    """
    from_domain = _domain_of(sender)
    if from_domain in senders.google_security:
        kind = PinnedKind.GOOGLE_SECURITY
    elif from_domain in senders.sign_in:
        kind = PinnedKind.SIGN_IN_CODE
    else:
        return None
    return kind if _gmail_vouches(auth_results, from_domain) else None


def _skip_quoted(text: str, start: int) -> int | None:
    """Index just after the quoted string that opens at ``start``, ``None`` when it is never closed."""
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 1
        elif text[index] == '"':
            return index + 1
        index += 1
    return None


def _skip_comment(text: str, start: int) -> int | None:
    """Index just after the (nested) comment that opens at ``start``, ``None`` when it is never closed."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 1
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _split_results(header: str) -> list[str] | None:
    """Split an ``Authentication-Results`` value at its top-level semicolons (RFC 8601, comments as RFC 5322).

    Comments (nested, with backslash escapes) are dropped and quoted strings (with escapes) are made opaque, so text
    inside them can neither end a part nor pose as a result. ``None`` when the header is ambiguous: an unterminated
    comment or quote, or a closing parenthesis without an opening one.
    """
    parts: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(header):
        char = header[index]
        if char == ")":
            return None
        if char in '("':
            end = _skip_comment(header, index) if char == "(" else _skip_quoted(header, index)
            if end is None:
                return None
            current.append(" " if char == "(" else _QUOTED)
            index = end
            continue
        if char == ";":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _gmail_vouches(auth_results: Sequence[str], from_domain: str) -> bool:
    """Fail closed: exactly one ``dmarc`` result in the topmost block, written by ``mx.google.com``."""
    if not auth_results:
        return False
    split = _split_results(auth_results[0])
    if split is None:
        return False
    server, *parts = split
    tokens = server.split()
    if not tokens or tokens[0].casefold() != GMAIL_AUTHSERV_ID:
        return False
    if sum(len(_DMARC_ANYWHERE.findall(part)) for part in parts) != 1:
        return False
    for part in parts:
        match = _DMARC.match(part)
        if match is None:
            continue
        domains = _HEADER_FROM.findall(match.group("rest"))
        return match.group("result").casefold() == "pass" and len(domains) == 1 and domains[0].casefold() == from_domain
    return False
