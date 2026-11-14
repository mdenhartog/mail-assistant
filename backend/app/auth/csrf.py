# pure module (mutation-gated)
"""CSRF token derivation and the Origin / Fetch-Metadata rules (W-4). No I/O, no clock, no framework."""

import hashlib
import hmac
from urllib.parse import urlsplit

SAME_ORIGIN = "same-origin"


def csrf_token(key: bytes, session_id: str) -> str:
    """Derive the token of a session: the hex HMAC-SHA-256 of the session id under the CSRF key."""
    return hmac.new(key, session_id.encode("utf-8"), hashlib.sha256).hexdigest()


def token_valid(key: bytes, session_id: str, presented: str | None) -> bool:
    """Compare a presented token with the session's token in constant time; a missing token is refused."""
    if presented is None:
        return False
    return hmac.compare_digest(csrf_token(key, session_id).encode("utf-8"), presented.encode("utf-8"))


def origin_ok(public_origin: str, origin: str | None) -> bool:
    """Accept only an ``Origin`` header that equals the public origin exactly (``scheme://host[:port]``)."""
    if origin is None:
        return False
    parts = urlsplit(public_origin)
    return origin == f"{parts.scheme}://{parts.netloc}"


def fetch_site_ok(value: str | None) -> bool:
    """Accept a missing ``Sec-Fetch-Site`` (non-browser client) or ``same-origin``; anything else is refused."""
    return value is None or value == SAME_ORIGIN
