# pure module (mutation-gated)
"""The client address: what the last trusted proxy appended, else the peer itself (U-web-settings-24, ADR-0034)."""

from collections.abc import Sequence

UNKNOWN_CLIENT = "unknown"


def client_key(peer: str | None, xff: str | None, trusted_cidrs: Sequence[str], hops: int) -> str:
    """Return the key of the client of a request."""
    raise NotImplementedError
