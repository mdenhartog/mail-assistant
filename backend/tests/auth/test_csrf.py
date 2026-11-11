"""U-web-settings-19: the pure CSRF derivation and the Origin / Fetch-Metadata rules (mutation-gated module)."""

import hashlib
import hmac

import pytest

from app.auth import csrf
from app.auth.csrf import csrf_token, fetch_site_ok, origin_ok, token_valid

KEY = b"k" * 32
SESSION = "a" * 64
OTHER_SESSION = "b" * 64
PUBLIC = "https://settings.example.test"


# Criterion 1
def test_given_a_session_id_when_the_token_is_derived_then_it_is_the_hmac_sha256_hex() -> None:
    expected = hmac.new(KEY, SESSION.encode("utf-8"), hashlib.sha256).hexdigest()

    assert csrf_token(KEY, SESSION) == expected
    assert len(csrf_token(KEY, SESSION)) == 64


def test_given_another_session_or_key_when_the_token_is_derived_then_it_differs() -> None:
    assert csrf_token(KEY, SESSION) != csrf_token(KEY, OTHER_SESSION)
    assert csrf_token(KEY, SESSION) != csrf_token(b"j" * 32, SESSION)
    assert csrf_token(KEY, SESSION) == csrf_token(KEY, SESSION)


def test_given_a_presented_token_when_compared_then_hmac_compare_digest_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return real(left, right)

    monkeypatch.setattr(csrf.hmac, "compare_digest", spy)  # pyright: ignore[reportAttributeAccessIssue]

    assert token_valid(KEY, SESSION, csrf_token(KEY, SESSION)) is True

    assert len(calls) == 1


def test_given_a_wrong_missing_or_foreign_token_when_checked_then_it_is_refused() -> None:
    good = csrf_token(KEY, SESSION)

    assert token_valid(KEY, SESSION, good) is True
    assert token_valid(KEY, SESSION, None) is False
    assert token_valid(KEY, SESSION, "") is False
    assert token_valid(KEY, SESSION, good[:-1]) is False
    assert token_valid(KEY, SESSION, good + "0") is False
    assert token_valid(KEY, SESSION, good.upper()) is False
    assert token_valid(KEY, SESSION, csrf_token(KEY, OTHER_SESSION)) is False
    assert token_valid(KEY, SESSION, csrf_token(b"j" * 32, SESSION)) is False


def test_given_a_non_ascii_token_when_checked_then_it_is_refused_without_an_error() -> None:
    assert token_valid(KEY, SESSION, "tökén") is False


# Criterion 5
def test_given_the_public_origin_when_the_origin_header_equals_it_then_it_is_accepted() -> None:
    assert origin_ok(PUBLIC, PUBLIC) is True


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "null",
        "http://settings.example.test",
        "https://settings.example.test:8443",
        "https://other.example.test",
        "https://settings.example.test.evil.test",
        "https://evil.test/https://settings.example.test",
        "https://settings.example.test/",
        "https://SETTINGS.example.test",
        " https://settings.example.test",
    ],
)
def test_given_a_wrong_missing_or_null_origin_when_checked_then_it_is_refused(origin: str | None) -> None:
    assert origin_ok(PUBLIC, origin) is False


def test_given_a_public_origin_with_a_trailing_slash_when_checked_then_the_origin_form_is_compared() -> None:
    assert origin_ok(PUBLIC + "/", PUBLIC) is True
    assert origin_ok(PUBLIC + "/path", PUBLIC) is True
    assert origin_ok(PUBLIC + "/", "https://other.example.test") is False


@pytest.mark.parametrize("value", [None, "same-origin"])
def test_given_no_header_or_same_origin_when_checked_then_the_fetch_site_is_accepted(value: str | None) -> None:
    assert fetch_site_ok(value) is True


@pytest.mark.parametrize("value", ["cross-site", "same-site", "none", "", "Same-Origin", "unknown"])
def test_given_any_other_fetch_site_when_checked_then_it_is_refused(value: str) -> None:
    assert fetch_site_ok(value) is False
