# pure module (mutation-gated)
"""Keyed hash and constant-time check of the six-digit sign-in code (ADR-0036, W-1)."""

import hashlib
import hmac
import re

CODE_PATTERN = re.compile(r"[0-9]{6}")
_LENGTH_BYTES = 4


def hash_code(key: bytes, request_id: str, code: str) -> bytes:
    """HMAC-SHA-256 over the length-prefixed request id and the code (fields cannot shift into each other)."""
    request = request_id.encode("utf-8")
    message = len(request).to_bytes(_LENGTH_BYTES, "big") + request + code.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).digest()


def verify_code(key: bytes, request_id: str, code: str, stored_hash: bytes) -> bool:
    """Return True when the code matches the stored hash; a malformed code is False, never an error."""
    if CODE_PATTERN.fullmatch(code) is None:
        return False
    return hmac.compare_digest(hash_code(key, request_id, code), stored_hash)
