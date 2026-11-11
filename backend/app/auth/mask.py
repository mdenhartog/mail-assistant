# pure module (mutation-gated)
"""Masked form of the sign-in address for responses (W-15)."""

MASK = "***"


def mask_address(address: str) -> str:
    """Return `m***@example.com`; an address without local part or domain gives only `***`."""
    local, separator, domain = address.rpartition("@")
    if not separator or not local or not domain:
        return MASK
    return local[0] + MASK + separator + domain
