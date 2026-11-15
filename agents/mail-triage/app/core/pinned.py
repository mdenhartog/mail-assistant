"""Pinned mail: the app's own sign-in mail and Google security mail never leave the inbox (AC-39, MC-19, ADR-0045).

The two kinds are told apart by their own allow-list, because they are treated differently afterwards: Google security
mail raises an alert, the sign-in code mail stays silent (ADR-0048).

The decision rests on Gmail's own verdict, never on the model or on the list. Only the topmost
``Authentication-Results`` header counts, because mail servers add theirs on top and a sender can only forge headers
below it. The header must name ``mx.google.com`` as its server, show ``dmarc=pass`` and a ``header.from`` domain that
is the domain of the From address and is on the configured allow-list.
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
_COMMENT = re.compile(r"\([^)]*\)")
_DMARC = re.compile(r"^\s*dmarc\s*=\s*(?P<result>[a-z]+)(?P<rest>.*)$", re.IGNORECASE | re.DOTALL)
_HEADER_FROM = re.compile(r"(?:^|\s)header\.from\s*=\s*(?P<domain>[^\s;]+)", re.IGNORECASE)


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


def _gmail_vouches(auth_results: Sequence[str], from_domain: str) -> bool:
    if not auth_results:
        return False
    server, *parts = _COMMENT.sub(" ", auth_results[0]).split(";")
    tokens = server.split()
    if not tokens or tokens[0].casefold() != GMAIL_AUTHSERV_ID:
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
