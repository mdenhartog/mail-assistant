import hashlib
import hmac
import re
from unittest.mock import patch

import pytest

from app.auth import code_hash
from app.auth.code_hash import hash_code, verify_code
from app.auth.digest import UPDATED_BY_PREFIX, updated_by, username_digest
from app.auth.mask import mask_address
from app.auth.return_to import DEFAULT_RETURN_TO, safe_return_to

KEY = b"k" * 32
OTHER_KEY = b"o" * 32
REQUEST_ID = "req-1"


def test_hash_is_stable_32_bytes_and_depends_on_every_input() -> None:
    first = hash_code(KEY, REQUEST_ID, "123456")
    assert first == hash_code(KEY, REQUEST_ID, "123456")
    assert isinstance(first, bytes)
    assert len(first) == 32
    assert first != hash_code(OTHER_KEY, REQUEST_ID, "123456")
    assert first != hash_code(KEY, "req-2", "123456")
    assert first != hash_code(KEY, REQUEST_ID, "123457")


def test_hash_is_hmac_sha256_over_unambiguous_fields() -> None:
    # Canaries: the fields cannot be shifted into each other, not even with a NUL in the id.
    assert hash_code(KEY, "ab", "123456") != hash_code(KEY, "a", "b123456")
    assert hash_code(KEY, "a\x00b", "123456") != hash_code(KEY, "a", "b\x00123456")
    expected = hmac.new(KEY, len(b"req-1").to_bytes(4, "big") + b"req-1" + b"123456", hashlib.sha256).digest()
    assert hash_code(KEY, REQUEST_ID, "123456") == expected


def test_verify_accepts_the_right_code_and_refuses_a_neighbour() -> None:
    stored = hash_code(KEY, REQUEST_ID, "123456")
    assert verify_code(KEY, REQUEST_ID, "123456", stored) is True
    assert verify_code(KEY, REQUEST_ID, "123457", stored) is False
    assert verify_code(OTHER_KEY, REQUEST_ID, "123456", stored) is False
    assert verify_code(KEY, "req-2", "123456", stored) is False


@pytest.mark.parametrize(
    "bad",
    ["", " 123456", "123456 ", "123 456", "12345a", "abcdef", "12345", "1234567", "١٢٣٤٥٦", "²²²²²²", "123456\n"],
)
def test_verify_refuses_malformed_codes_without_an_exception(bad: str) -> None:
    stored = hash_code(KEY, REQUEST_ID, bad)
    assert verify_code(KEY, REQUEST_ID, bad, stored) is False


def test_verify_refuses_a_stored_hash_of_the_wrong_length() -> None:
    assert verify_code(KEY, REQUEST_ID, "123456", b"") is False


def test_verify_uses_compare_digest_and_not_equality() -> None:
    stored = hash_code(KEY, REQUEST_ID, "123456")
    candidate = hash_code(KEY, REQUEST_ID, "123456")
    with patch.object(code_hash.hmac, "compare_digest", wraps=hmac.compare_digest) as spy:
        assert verify_code(KEY, REQUEST_ID, "123456", stored) is True
        assert verify_code(KEY, REQUEST_ID, "123450", stored) is False
    assert spy.call_count == 2
    assert spy.call_args_list[0].args == (candidate, stored)
    assert spy.call_args_list[1].args == (hash_code(KEY, REQUEST_ID, "123450"), stored)


def test_verify_result_follows_compare_digest() -> None:
    stored = hash_code(KEY, REQUEST_ID, "123456")
    with patch.object(code_hash.hmac, "compare_digest", return_value=False):
        assert verify_code(KEY, REQUEST_ID, "123456", stored) is False
    with patch.object(code_hash.hmac, "compare_digest", return_value=True):
        assert verify_code(KEY, REQUEST_ID, "123450", stored) is True


@pytest.mark.parametrize(
    ("address", "masked"),
    [
        ("marco@example.com", "m***@example.com"),
        ("a@example.com", "a***@example.com"),
        ("very.long.name@sub.example.org", "v***@sub.example.org"),
        ("odd@name@example.com", "o***@example.com"),
    ],
)
def test_mask_keeps_first_letter_and_domain_only(address: str, masked: str) -> None:
    assert mask_address(address) == masked


def test_mask_never_shows_the_local_part() -> None:
    assert "arco" not in mask_address("marco@example.com")
    assert "ery.long" not in mask_address("very.long.name@sub.example.org")


@pytest.mark.parametrize("address", ["", "nobody", "@example.com", "marco@", "@"])
def test_mask_of_a_malformed_address_reveals_nothing(address: str) -> None:
    assert mask_address(address) == "***"


def test_username_digest_is_keyed_stable_lower_hex_and_hides_the_name() -> None:
    digest = username_digest(KEY, "canary-user")
    assert digest == username_digest(KEY, "canary-user")
    assert re.fullmatch(r"[0-9a-f]{32}", digest)
    assert digest != username_digest(OTHER_KEY, "canary-user")
    assert digest != username_digest(KEY, "other-user")
    assert "canary" not in digest
    assert digest == hmac.new(KEY, b"canary-user", hashlib.sha256).hexdigest()[:32]


def test_updated_by_carries_the_prefixed_digest() -> None:
    assert UPDATED_BY_PREFIX == "web:"
    assert updated_by(KEY, "canary-user") == "web:" + username_digest(KEY, "canary-user")


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example",
        "//evil.example",
        "/\\evil",
        "javascript:alert(1)",
        "/settings/../x",
        "/other",
        "",
        None,
        "/settings?x=1",
        "/settings/",
        " /settings",
        "/SETTINGS",
    ],
)
def test_return_to_falls_back_to_settings(value: str | None) -> None:
    assert safe_return_to(value) == "/settings"


def test_return_to_keeps_settings() -> None:
    assert DEFAULT_RETURN_TO == "/settings"
    assert safe_return_to("/settings") == "/settings"
