"""A PostgreSQL SCRAM-SHA-256 verifier computed on the client (ADR-0030).

The migrate job sends this verifier in ``PASSWORD '...'`` instead of the clear password, so the password never reaches
the server, its statement log or ``pg_stat_activity``. Format:
``SCRAM-SHA-256$<iterations>:<salt>$<StoredKey>:<ServerKey>`` (RFC 5802 / RFC 7677, base64 values).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ITERATIONS = 4096  # the PostgreSQL default (scram_iterations)
SALT_BYTES = 16


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _hmac(key: bytes, message: bytes) -> bytes:
    return hmac.new(key, message, hashlib.sha256).digest()


def scram_verifier(password: str, salt: bytes, iterations: int = ITERATIONS) -> str:
    """The verifier for a given salt. Pure: the salt is a parameter so a test can use the RFC 7677 vector."""
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    stored_key = hashlib.sha256(_hmac(salted, b"Client Key")).digest()
    server_key = _hmac(salted, b"Server Key")
    return f"SCRAM-SHA-256${iterations}:{_b64(salt)}${_b64(stored_key)}:{_b64(server_key)}"


def verifier_for(password: str) -> str:
    """The verifier with a fresh random salt: what the migrate job sends."""
    return scram_verifier(password, secrets.token_bytes(SALT_BYTES))
