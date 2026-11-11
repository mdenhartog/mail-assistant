# pure module (mutation-gated)
"""CSRF token derivation and the Origin / Fetch-Metadata rules (W-4). Skeleton: the rules follow in the next commit."""

import hmac

_COMPARE = hmac.compare_digest  # the rules of the next commit compare in constant time


def csrf_token(key: bytes, session_id: str) -> str:
    """Derive the token of a session."""
    raise NotImplementedError


def token_valid(key: bytes, session_id: str, presented: str | None) -> bool:
    """Compare a presented token with the derived one."""
    raise NotImplementedError


def origin_ok(public_origin: str, origin: str | None) -> bool:
    """Compare the Origin header with the public origin."""
    raise NotImplementedError


def fetch_site_ok(value: str | None) -> bool:
    """Accept a missing or same-origin Sec-Fetch-Site."""
    raise NotImplementedError
