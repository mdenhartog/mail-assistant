"""U-label-structure-07 (R1, ADR-0054): one verifier tells whether Gmail itself authenticated the From domain."""

from __future__ import annotations

import pytest

from app.core.authentication import authenticated_from_domain
from tests.fakes.gmail_headers import RawHeaders, fixture_names, load_fixture

DOMAIN = "example.com"
FROM = f"Test Sender <sender@{DOMAIN}>"


def _gmail(result: str, *, domain: str = DOMAIN) -> str:
    return f"mx.google.com; {result} header.from={domain}"


def _headers(*auth: str, sender: str = FROM) -> RawHeaders:
    return (*(("Authentication-Results", value) for value in auth), ("From", sender))


def _from_of(headers: RawHeaders) -> str | None:
    values = [value for name, value in headers if name.casefold() == "from"]
    return values[0] if values else None


def test_given_a_topmost_gmail_pass_with_the_matching_header_from_when_verified_then_the_domain_is_returned() -> None:
    headers = _headers(_gmail("dmarc=pass"))

    assert authenticated_from_domain(headers, FROM) == DOMAIN


def test_given_a_mixed_case_from_domain_when_verified_then_the_domain_is_lower_case() -> None:
    headers = _headers(_gmail("dmarc=pass", domain="Example.COM"), sender="A <a@EXAMPLE.com>")

    assert authenticated_from_domain(headers, "A <a@EXAMPLE.com>") == DOMAIN


@pytest.mark.parametrize(
    ("from_domain", "header_from", "expected"),
    [
        pytest.param("straße-bank.de", "straße-bank.de", None, id="sharp-s-vs-ss"),
        pytest.param("strasse-bank.de", "straße-bank.de", None, id="ss-from-sharp-s-header"),
        pytest.param("straße-bank.de", "strasse-bank.de", None, id="sharp-s-from-ss-header"),
        pytest.param("ςigma.example", "ςigma.example", None, id="final-sigma"),
        pytest.param("\u03c3igma.example", "ςigma.example", None, id="sigma-vs-final-sigma"),
        pytest.param("ﬀ-bank.example", "ﬀ-bank.example", None, id="ligature-ff"),
        pytest.param("ff-bank.example", "ﬀ-bank.example", None, id="ff-vs-ligature"),
        pytest.param("İbank.example", "İbank.example", "xn--ibank-7fd.example", id="dotted-capital-i-stays-distinct"),
        pytest.param("ibank.example", "İbank.example", None, id="i-vs-dotted-capital-i"),
        pytest.param("example.com", "example.com", "example.com", id="plain-ascii"),
        pytest.param("EXAMPLE.Com", "example.COM", "example.com", id="uppercase-ascii"),
        pytest.param("xn--bcher-kva.example", "xn--bcher-kva.example", "xn--bcher-kva.example", id="a-label"),
        pytest.param("bücher.example", "xn--bcher-kva.example", "xn--bcher-kva.example", id="u-label-vs-a-label"),
        pytest.param("xn--bcher-kva.example", "bücher.example", "xn--bcher-kva.example", id="a-label-vs-u-label"),
        pytest.param("exa mple.com", "exa mple.com", None, id="unconvertible"),
    ],
)
def test_given_a_unicode_from_domain_when_verified_then_only_the_exact_a_label_matches_and_is_returned(
    from_domain: str, header_from: str, expected: str | None
) -> None:
    sender = f"A <billing@{from_domain}>"
    headers = _headers(_gmail("dmarc=pass", domain=header_from), sender=sender)

    assert authenticated_from_domain(headers, sender) == expected


@pytest.mark.parametrize(
    "auth",
    [
        pytest.param(("spamfilter.example; dmarc=pass header.from=example.com",), id="not-gmail"),
        pytest.param(("mx.google.com.evil.example; dmarc=pass header.from=example.com",), id="lookalike-server"),
        pytest.param(
            ("mx.google.com; spf=pass (dmarc=pass header.from=example.com) header.from=example.com",), id="comment"
        ),
        pytest.param(("mx.google.com; arc=pass dmarc=pass header.from=example.com",), id="arc-result"),
        pytest.param(
            ("mx.google.com; dmarc=pass header.from=example.com; dmarc=pass header.from=example.com",), id="two-dmarc"
        ),
        pytest.param(("mx.google.com; dmarc=fail header.from=example.com",), id="fail"),
        pytest.param(("mx.google.com; dmarc=pass header.from=example.net",), id="other-header-from"),
        pytest.param(("mx.google.com; spf=pass smtp.mailfrom=example.com",), id="no-dmarc"),
        pytest.param(
            ("mx.google.com; dmarc=fail header.from=example.com", "mx.google.com; dmarc=pass header.from=example.com"),
            id="pass-only-below",
        ),
        pytest.param((), id="no-header"),
    ],
)
def test_given_a_header_that_does_not_vouch_when_verified_then_the_result_is_none(auth: tuple[str, ...]) -> None:
    assert authenticated_from_domain(_headers(*auth), FROM) is None


def test_given_dmarc_pass_only_in_x_original_or_arc_headers_when_verified_then_the_result_is_none() -> None:
    value = _gmail("dmarc=pass")
    headers = (
        ("X-Original-Authentication-Results", value),
        ("ARC-Authentication-Results", f"i=1; {value}"),
        ("From", FROM),
    )

    assert authenticated_from_domain(headers, FROM) is None


def test_given_a_header_name_in_other_case_when_verified_then_it_is_still_the_authentication_results() -> None:
    headers = (("authentication-RESULTS", _gmail("dmarc=pass")), ("From", FROM))

    assert authenticated_from_domain(headers, FROM) == DOMAIN


@pytest.mark.parametrize("name", ["forged_auth_results", "non_gmail_auth_results", "missing_auth_results"])
def test_given_a_sender_written_or_missing_header_when_verified_then_the_result_is_none(name: str) -> None:
    headers = load_fixture(name).headers

    assert authenticated_from_domain(headers, _from_of(headers)) is None


def test_given_a_sender_written_gmail_look_alike_below_a_failing_gmail_header_when_verified_then_none() -> None:
    headers = _headers(_gmail("dmarc=fail"), _gmail("dmarc=pass"))

    assert authenticated_from_domain(headers, FROM) is None


def test_given_dmarc_pass_only_in_an_attached_message_when_verified_then_the_result_is_none() -> None:
    fixture = load_fixture("attached_rfc822")
    assert fixture.attached is not None

    assert authenticated_from_domain(fixture.headers, _from_of(fixture.headers)) is None


@pytest.mark.parametrize("name", ["several_auth_results", "folded_auth_results"])
def test_given_the_non_gmail_fixtures_when_verified_then_the_result_is_none(name: str) -> None:
    headers = load_fixture(name).headers

    assert authenticated_from_domain(headers, _from_of(headers)) is None


@pytest.mark.parametrize(
    "sender",
    [None, "", "no address here", "a@example.com, b@example.net", "Name <>", "<@>"],
)
def test_given_a_missing_or_unparsable_from_when_verified_then_the_result_is_none(sender: str | None) -> None:
    headers = (("Authentication-Results", _gmail("dmarc=pass")),)

    assert authenticated_from_domain(headers, sender) is None


def test_given_several_from_headers_when_verified_then_the_result_is_none() -> None:
    headers = (
        ("Authentication-Results", _gmail("dmarc=pass")),
        ("From", FROM),
        ("From", "Other <other@example.net>"),
    )

    assert authenticated_from_domain(headers, FROM) is None


def test_given_the_fixture_with_several_from_when_verified_then_the_result_is_none() -> None:
    headers = load_fixture("several_from").headers

    assert authenticated_from_domain(headers, _from_of(headers)) is None


def test_given_the_fixture_without_from_when_verified_then_the_result_is_none() -> None:
    headers = load_fixture("no_from").headers

    assert authenticated_from_domain(headers, _from_of(headers)) is None


def test_given_the_real_gmail_shape_when_verified_then_the_from_domain_is_returned() -> None:
    headers = load_fixture("gmail_real_shape").headers

    assert authenticated_from_domain(headers, _from_of(headers)) == DOMAIN


def test_given_the_real_gmail_shape_with_another_from_domain_when_verified_then_the_result_is_none() -> None:
    headers = load_fixture("gmail_real_shape").headers

    assert authenticated_from_domain(headers, "Test Sender <sender@example.net>") is None


def test_every_stored_fixture_has_an_expected_result() -> None:
    expected = {"gmail_real_shape"}
    verified = {
        name
        for name in fixture_names()
        if authenticated_from_domain(load_fixture(name).headers, _from_of(load_fixture(name).headers)) is not None
    }

    assert verified == expected
