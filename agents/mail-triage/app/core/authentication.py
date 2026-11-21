"""The one check that Gmail itself authenticated the sender of a mail (ADR-0054, ADR-0045, ADR-0048).

The ``From`` header is written by the sender, so it proves nothing. Only the topmost ``Authentication-Results``
header counts, because mail servers add theirs on top and a sender can only forge headers below it. The header must
name ``mx.google.com`` as its server, show exactly one ``dmarc`` result that is ``pass`` and a ``header.from`` that is
the domain of the one ``From`` address. Anything else, including a header this module cannot read with certainty, is
"not authenticated". ``ARC-Authentication-Results`` and ``X-Original-Authentication-Results`` are other headers and
never count, and the caller passes the headers of the mail itself, never those of an attached ``message/rfc822``.

The header is tokenised as RFC 8601 says (nested comments, quoted strings, escapes).
"""

from __future__ import annotations

import re
from email.utils import getaddresses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["GMAIL_AUTHSERV_ID", "authenticated_from_domain"]

GMAIL_AUTHSERV_ID = "mx.google.com"
_AUTH_RESULTS = "authentication-results"
_FROM = "from"
_DMARC_ANYWHERE = re.compile(r"(?<![\w.-])dmarc\s*=", re.IGNORECASE)
_DMARC = re.compile(r"^\s*dmarc\s*=\s*(?P<result>[a-z]+)(?P<rest>.*)$", re.IGNORECASE | re.DOTALL)
_HEADER_FROM = re.compile(r"(?:^|\s)header\.from\s*=\s*(?P<domain>[^\s;]+)", re.IGNORECASE)
_QUOTED = '"_"'  # what a quoted string becomes: its content can never look like a result or a domain


def authenticated_from_domain(headers: Sequence[tuple[str, str]], from_header: str | None) -> str | None:
    """The lower-case domain of the one ``From`` address when Gmail vouches for it (DMARC pass), else ``None``.

    Args:
        headers: The ``(name, value)`` header pairs of the mail in message order, topmost first, duplicates kept.
        from_header: The value of its ``From`` header.

    Returns:
        The ``From`` domain, or ``None`` for anything that is not an unambiguous Gmail verdict for that domain.
    """
    if from_header is None or sum(1 for name, _ in headers if name.casefold() == _FROM) > 1:
        return None
    domain = _from_domain(from_header)
    if domain is None:
        return None
    topmost = next((value for name, value in headers if name.casefold() == _AUTH_RESULTS), None)
    if topmost is None or not _gmail_vouches(topmost, domain):
        return None
    return domain


def _from_domain(from_header: str) -> str | None:
    """The domain of the single address in a ``From`` value, ``None`` for none, several or an unreadable one."""
    addresses = [address for _, address in getaddresses([from_header], strict=True) if address]
    if len(addresses) != 1:
        return None
    local, separator, domain = addresses[0].rpartition("@")
    domain = domain.strip().casefold()
    return domain if separator and local and domain else None


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


def _gmail_vouches(header: str, from_domain: str) -> bool:
    """Fail closed: exactly one ``dmarc`` result in the block, written by ``mx.google.com``."""
    split = _split_results(header)
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
