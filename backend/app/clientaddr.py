# pure module (mutation-gated)
"""The client address: what the last trusted proxy appended, else the peer itself (U-web-settings-24, ADR-0034)."""

import ipaddress
from collections.abc import Sequence

UNKNOWN_CLIENT = "unknown"
IPV6_PREFIX = 64
IPV6_SITE_PREFIX = 48


def _parse(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the address of a text, with an IPv4-mapped IPv6 address as the IPv4 address, or None."""
    try:
        address = ipaddress.ip_address(text.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _key_of(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Return an IPv4 address as itself and an IPv6 address as its /64 network, the unit one subscriber holds."""
    if isinstance(address, ipaddress.IPv4Address):
        return str(address)
    return str(ipaddress.ip_network((address, IPV6_PREFIX), strict=False))


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
        An IPv4 address in canonical form, an IPv6 address as its /64 network (``2001:db8:0:1::/64``), the peer text
        itself when it is no address, or ``unknown``.
    """
    if peer is None:
        return UNKNOWN_CLIENT
    address = _parse(peer)
    if address is None:
        return peer
    if not _trusted(address, trusted_cidrs) or not xff or hops < 1:
        return _key_of(address)
    entries = xff.split(",")
    if len(entries) < hops:
        return _key_of(address)
    forwarded = _parse(entries[-hops])
    return _key_of(address) if forwarded is None else _key_of(forwarded)


def ipv6_prefix48(client: str) -> str | None:
    """Return the /48 network of an IPv6 client key (a /64 network), or None for any other key.

    The /48 is what one site or subscriber holds, so a flood of /64 keys from it can be bounded as one group.
    """
    try:
        network = ipaddress.ip_network(client)
    except ValueError:
        return None
    if not isinstance(network, ipaddress.IPv6Network) or network.prefixlen not in {IPV6_PREFIX}:
        return None
    return str(network.supernet(new_prefix=IPV6_SITE_PREFIX))
