# pure module (mutation-gated)
"""The client address: what the last trusted proxy appended, else the peer itself (U-web-settings-24, ADR-0034)."""

import ipaddress
from collections.abc import Sequence

UNKNOWN_CLIENT = "unknown"


def _parse(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the address of a text, with an IPv4-mapped IPv6 address as the IPv4 address, or None."""
    try:
        address = ipaddress.ip_address(text.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _trusted(address: ipaddress.IPv4Address | ipaddress.IPv6Address, cidrs: Sequence[str]) -> bool:
    return any(address in ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


def client_key(peer: str | None, xff: str | None, trusted_cidrs: Sequence[str], hops: int) -> str:
    """Return the key of the client of a request.

    A peer outside the trusted CIDRs is keyed by its own address and its header is ignored. For a trusted peer the key
    is the entry ``hops`` from the right of ``X-Forwarded-For``, the one the last trusted proxy appended; a missing,
    short or unreadable header gives the peer's own address, so a spoofed value never opens a fresh bucket.

    Args:
        peer: The address of the connection, or None.
        xff: The ``X-Forwarded-For`` values joined with commas, or None.
        trusted_cidrs: The networks of the trusted proxies.
        hops: How many trusted proxies stand in front of the app.

    Returns:
        The address in one canonical form, the peer text itself when it is no address, or ``unknown``.
    """
    if peer is None:
        return UNKNOWN_CLIENT
    address = _parse(peer)
    if address is None:
        return peer
    if not _trusted(address, trusted_cidrs) or not xff or hops < 1:
        return str(address)
    entries = xff.split(",")
    if len(entries) < hops:
        return str(address)
    forwarded = _parse(entries[-hops])
    return str(address) if forwarded is None else str(forwarded)
