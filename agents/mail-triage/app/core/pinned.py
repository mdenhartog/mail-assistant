"""Pinned mail: the app's own sign-in mail and Google security mail never leave the inbox (AC-39, MC-19, ADR-0045).

The decision rests on Gmail's own verdict, never on the model or on the list. Only the topmost
``Authentication-Results`` header counts, because mail servers add theirs on top and a sender can only forge headers
below it. The header must name ``mx.google.com`` as its server, show ``dmarc=pass`` and a ``header.from`` domain that
is the domain of the From address and is on the configured allow-list.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

__all__ = ["GMAIL_AUTHSERV_ID", "is_pinned"]

GMAIL_AUTHSERV_ID = "mx.google.com"
_COMMENT = re.compile(r"\([^)]*\)")
_DMARC = re.compile(r"^\s*dmarc\s*=\s*(?P<result>[a-z]+)(?P<rest>.*)$", re.IGNORECASE | re.DOTALL)
_HEADER_FROM = re.compile(r"(?:^|\s)header\.from\s*=\s*(?P<domain>[^\s;]+)", re.IGNORECASE)


def _domain_of(address: str) -> str:
    return address.rpartition("@")[2].strip().casefold()


def is_pinned(auth_results: Sequence[str], sender: str, allowed_domains: Collection[str]) -> bool:
    """True when Gmail vouches (DMARC pass) for a From domain on the allow-list.

    ``auth_results`` holds the ``Authentication-Results`` values in header order, topmost first; ``sender`` is the
    parsed From address.
    """
    if not auth_results:
        return False
    server, *parts = _COMMENT.sub(" ", auth_results[0]).split(";")
    tokens = server.split()
    if not tokens or tokens[0].casefold() != GMAIL_AUTHSERV_ID:
        return False
    from_domain = _domain_of(sender)
    allowed = {domain.casefold() for domain in allowed_domains}
    if not from_domain or from_domain not in allowed:
        return False
    for part in parts:
        match = _DMARC.match(part)
        if match is None:
            continue
        header_from = _HEADER_FROM.search(match.group("rest"))
        return (
            match.group("result").casefold() == "pass"
            and header_from is not None
            and header_from.group("domain").casefold() == from_domain
        )
    return False
