"""Parse SPF, DKIM and DMARC results from the Authentication-Results header (spec: AC-16 warnings, U-12)."""

from __future__ import annotations

import pytest

from app.core.alert_text import AuthResults
from app.core.auth_results import parse_auth_results

GOOGLE = (
    "mx.google.com; dkim=pass header.i=@example.com header.s=s1; "
    "spf=pass (google.com: domain of a@example.com designates 1.2.3.4 as permitted sender); "
    "dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from=example.com"
)


def test_given_a_google_header_when_parsed_then_all_three_results_are_read() -> None:
    assert parse_auth_results(GOOGLE) == AuthResults(spf="pass", dkim="pass", dmarc="pass")


def test_given_failures_when_parsed_then_they_are_reported_per_method() -> None:
    header = "mx.example; spf=softfail smtp.mailfrom=x@y.z; dkim=none; dmarc=fail header.from=y.z"

    assert parse_auth_results(header) == AuthResults(spf="softfail", dkim="none", dmarc="fail")


@pytest.mark.parametrize("header", [None, "", "mx.example; auth=pass", "garbage"])
def test_given_no_usable_header_when_parsed_then_every_result_is_unknown(header: str | None) -> None:
    assert parse_auth_results(header) == AuthResults(None, None, None)


def test_given_a_forged_result_inside_a_comment_or_value_when_parsed_then_only_real_methods_count() -> None:
    header = "mx.example; spf=fail (comment says dkim=pass dmarc=pass)"

    result = parse_auth_results(header)

    assert result.spf == "fail"
    assert result.dkim is None
    assert result.dmarc is None


def test_given_a_repeated_method_when_parsed_then_the_first_result_wins() -> None:
    assert parse_auth_results("mx; spf=fail; spf=pass").spf == "fail"
