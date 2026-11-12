# pure module (mutation-gated)
"""Rule of the decoy login request (U-web-settings-50, ADR-0038): a stored hash that no code can ever match."""

from app.auth.code_hash import hash_code

DECOY_INPUT = "decoy"


def decoy_hash(key: bytes, request_id: str) -> bytes:
    """Return the hash stored for a decoy login request."""
    return hash_code(key, request_id, "")  # skeleton: the marker is not used yet
