# pure module (mutation-gated)
"""Keyed digest of a username, for security events and `updated_by` (W-10, W-15)."""

import hashlib
import hmac

UPDATED_BY_PREFIX = "web:"
DIGEST_LENGTH = 32


def username_digest(key: bytes, username: str) -> str:
    """Return 32 lower-case hex characters of the HMAC-SHA-256 of the username."""
    return hmac.new(key, username.encode("utf-8"), hashlib.sha256).hexdigest()[:DIGEST_LENGTH]


def updated_by(key: bytes, username: str) -> str:
    """Return the `updated_by` value `web:<32 hex>`."""
    return UPDATED_BY_PREFIX + username_digest(key, username)
