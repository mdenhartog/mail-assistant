"""U-label-structure-07: pinned mail takes its verdict from the one verifier of ADR-0054, with no parser of its own."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core import pinned
from app.core.pinned import PinnedKind, PinnedSenders, pinned_kind
from tests.fakes.gmail_headers import load_fixture

if TYPE_CHECKING:
    import pytest

ALLOW = PinnedSenders(google_security=frozenset({"accounts.google.com"}), sign_in=frozenset({"example.com"}))


def test_given_a_listed_sender_when_checked_then_the_shared_verifier_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[tuple[str, str], ...], str | None]] = []

    def verifier(headers: tuple[tuple[str, str], ...], from_header: str | None) -> str | None:
        calls.append((headers, from_header))
        return "accounts.google.com"

    monkeypatch.setattr(pinned, "authenticated_from_domain", verifier)

    kind = pinned_kind(("whatever",), "no-reply@accounts.google.com", ALLOW)

    assert kind is PinnedKind.GOOGLE_SECURITY
    assert calls == [((("Authentication-Results", "whatever"),), "no-reply@accounts.google.com")]


def test_given_the_verifier_does_not_vouch_when_checked_then_the_mail_is_not_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def verifier(headers: tuple[tuple[str, str], ...], from_header: str | None) -> str | None:
        del headers, from_header
        return None

    monkeypatch.setattr(pinned, "authenticated_from_domain", verifier)

    assert (
        pinned_kind(("mx.google.com; dmarc=pass header.from=accounts.google.com",), "a@accounts.google.com", ALLOW)
        is None
    )


def test_given_a_real_gmail_header_for_a_listed_domain_when_checked_then_the_mail_is_pinned() -> None:
    values = tuple(v for n, v in load_fixture("gmail_real_shape").headers if n == "Authentication-Results")

    assert pinned_kind(values, "sender@example.com", ALLOW) is PinnedKind.SIGN_IN_CODE


def test_pinned_has_no_header_parser_of_its_own() -> None:
    assert not hasattr(pinned, "_gmail_vouches")
    assert not hasattr(pinned, "_split_results")
