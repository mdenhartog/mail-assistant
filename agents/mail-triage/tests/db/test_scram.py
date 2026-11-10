"""U-quiet-hours-16b: the SCRAM-SHA-256 verifier the migrate job sends instead of the clear password (ADR-0030)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

from app.db.scram import ITERATIONS, scram_verifier, verifier_for

# RFC 7677 section 3: user "user", password "pencil", 4096 iterations.
RFC_SALT = base64.b64decode("W22ZaJ0SNY7soEsUEjb6gQ==")
RFC_AUTH_MESSAGE = (
    b"n=user,r=rOprNGfwEbeRWgbNEkqO,"
    b"r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096,"
    b"c=biws,r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0"
)
RFC_CLIENT_PROOF = base64.b64decode("dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ=")
RFC_SERVER_SIGNATURE = base64.b64decode("6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4=")


def _parts(verifier: str) -> tuple[int, bytes, bytes, bytes]:
    match = re.fullmatch(r"SCRAM-SHA-256\$(\d+):([^$]+)\$([^:]+):(.+)", verifier)
    assert match is not None, "not in the PostgreSQL SCRAM format"
    iterations, salt, stored, server = match.groups()
    return int(iterations), base64.b64decode(salt), base64.b64decode(stored), base64.b64decode(server)


def test_given_the_rfc_7677_vector_when_the_verifier_is_computed_then_it_proves_the_rfc_exchange() -> None:
    iterations, salt, stored_key, server_key = _parts(scram_verifier("pencil", RFC_SALT, 4096))

    assert (iterations, salt) == (4096, RFC_SALT)
    server_signature = hmac.new(server_key, RFC_AUTH_MESSAGE, hashlib.sha256).digest()
    assert server_signature == RFC_SERVER_SIGNATURE
    client_signature = hmac.new(stored_key, RFC_AUTH_MESSAGE, hashlib.sha256).digest()
    client_key = bytes(a ^ b for a, b in zip(RFC_CLIENT_PROOF, client_signature, strict=True))
    assert hashlib.sha256(client_key).digest() == stored_key


def test_given_the_same_password_when_two_verifiers_are_made_then_the_salts_differ_and_no_password_is_in_them() -> None:
    first, second = verifier_for("pencil"), verifier_for("pencil")

    assert first != second
    assert _parts(first)[0] == ITERATIONS == 4096
    assert "pencil" not in first
    assert len(_parts(first)[1]) == 16
