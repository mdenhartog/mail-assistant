"""U-mail-categories-05, criteria 4 and 5 (AC-39, MC-19): security mail is pinned by Gmail's verdict."""

from __future__ import annotations

import pytest

from app.core.pinned import PinnedKind, PinnedSenders, pinned_kind

ALLOW = PinnedSenders(google_security=frozenset({"accounts.google.com"}), sign_in=frozenset({"mail.example.test"}))
GOOD = "mx.google.com; spf=pass; dkim=pass header.i=@accounts.google.com; dmarc=pass (p=REJECT) header.from=accounts.google.com"  # noqa: E501
SENDER = "no-reply@accounts.google.com"


def test_given_google_security_mail_with_dmarc_pass_on_the_allow_list_then_it_is_pinned() -> None:
    assert pinned_kind((GOOD,), SENDER, ALLOW) is PinnedKind.GOOGLE_SECURITY


def test_given_the_apps_own_sign_in_mail_with_dmarc_pass_then_it_is_pinned() -> None:
    header = "mx.google.com; dmarc=pass header.from=mail.example.test"

    assert pinned_kind((header,), "login@mail.example.test", ALLOW) is PinnedKind.SIGN_IN_CODE


def test_given_a_forged_header_lower_in_the_mail_then_only_the_topmost_counts() -> None:
    real = "mx.google.com; dmarc=fail header.from=accounts.google.com"
    forged = GOOD

    assert pinned_kind((real, forged), SENDER, ALLOW) is None


@pytest.mark.parametrize(
    "header",
    [
        "evil.example; dmarc=pass header.from=accounts.google.com",  # not written by Google's receiving server
        "mx.google.com.evil.example; dmarc=pass header.from=accounts.google.com",  # look-alike authserv-id
        "mx.google.com; dmarc=fail header.from=accounts.google.com",
        "mx.google.com; dmarc=none header.from=accounts.google.com",
        "mx.google.com; spf=pass; dkim=pass",  # no dmarc result
        "mx.google.com; dmarc=pass header.from=other.example",  # header.from differs from the From domain
        "mx.google.com; dmarc=pass",  # no header.from
        "mx.google.com; spf=fail (dmarc=pass header.from=accounts.google.com)",  # inside a comment of another method
        "",
    ],
)
def test_given_a_header_that_does_not_prove_the_sender_then_it_is_not_pinned(header: str) -> None:
    assert pinned_kind((header,), SENDER, ALLOW) is None


def test_given_no_header_then_it_is_not_pinned() -> None:
    assert pinned_kind((), SENDER, ALLOW) is None


def test_given_a_sender_domain_off_the_allow_list_then_it_is_not_pinned() -> None:
    header = "mx.google.com; dmarc=pass header.from=news.example"

    assert pinned_kind((header,), "a@news.example", ALLOW) is None


def test_given_a_subdomain_of_an_allowed_domain_then_it_is_not_pinned() -> None:
    header = "mx.google.com; dmarc=pass header.from=evil.accounts.google.com"

    assert pinned_kind((header,), "a@evil.accounts.google.com", ALLOW) is None


def test_given_domain_case_differences_then_the_match_ignores_case() -> None:
    header = "mx.google.com; dmarc=pass header.from=Accounts.Google.com"

    assert pinned_kind((header,), "No-Reply@ACCOUNTS.google.com", ALLOW) is PinnedKind.GOOGLE_SECURITY


def test_given_a_domain_on_the_other_kinds_list_only_then_it_gets_that_kind_and_never_the_google_one() -> None:
    header = "mx.google.com; dmarc=pass header.from=accounts.google.com"
    only_sign_in = PinnedSenders(google_security=frozenset(), sign_in=frozenset({"accounts.google.com"}))

    assert pinned_kind((header,), SENDER, only_sign_in) is PinnedKind.SIGN_IN_CODE


def test_given_no_sign_in_domains_configured_then_the_apps_domain_is_not_pinned() -> None:
    header = "mx.google.com; dmarc=pass header.from=mail.example.test"
    google_only = PinnedSenders(google_security=frozenset({"accounts.google.com"}), sign_in=frozenset())

    assert pinned_kind((header,), "login@mail.example.test", google_only) is None
