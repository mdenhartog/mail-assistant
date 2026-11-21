"""Pinned mail: the app's own sign-in mail and Google security mail never leave the inbox (AC-39, MC-19, ADR-0045).

The two kinds are told apart by their own allow-list, because they are treated differently afterwards: Google security
mail raises an alert, the sign-in code mail stays silent (ADR-0048).

The decision rests on Gmail's own verdict, never on the model or on the list: ``authenticated_from_domain`` (ADR-0054)
is the one verifier, and the authenticated From domain must also be on the configured allow-list.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from app.core.authentication import authenticated_from_domain

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["PinnedKind", "PinnedSenders", "pinned_kind"]


class PinnedKind(StrEnum):
    """Which pinned kind a verified mail is."""

    GOOGLE_SECURITY = "google_security"
    SIGN_IN_CODE = "sign_in_code"


@dataclass(frozen=True, slots=True)
class PinnedSenders:
    """The sender domains of each pinned kind, lower case."""

    google_security: frozenset[str]
    sign_in: frozenset[str]


def pinned_kind(auth_results: Sequence[str], sender: str, senders: PinnedSenders) -> PinnedKind | None:
    """The pinned kind of a mail when Gmail vouches (DMARC pass) for a From domain on that kind's list, else ``None``.

    ``auth_results`` holds the ``Authentication-Results`` values in header order, topmost first; ``sender`` is the
    parsed From address.
    """
    headers = tuple(("Authentication-Results", value) for value in auth_results)
    domain = authenticated_from_domain(headers, sender)
    if domain is None:
        return None
    if domain in senders.google_security:
        return PinnedKind.GOOGLE_SECURITY
    if domain in senders.sign_in:
        return PinnedKind.SIGN_IN_CODE
    return None
