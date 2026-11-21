"""The RFC 8601 tokeniser and the verdict of pinned mail, case by case (AC-39, MC-19; mutation gate)."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.core import authentication
from app.core.pinned import PinnedKind, PinnedSenders, pinned_kind

SENDERS = PinnedSenders(google_security=frozenset({"google.test"}), sign_in=frozenset({"app.test", "mm.test"}))
SERVER = "mx.google.com"


def _kind(header: str, sender: str = "no-reply@google.test") -> PinnedKind | None:
    return pinned_kind([header], sender, SENDERS)


def test_given_a_quoted_string_when_skipped_then_the_index_after_its_closing_quote_is_returned() -> None:
    assert authentication._skip_quoted('x"ab"', 1) == 5
    assert authentication._skip_quoted('"ab"c', 0) == 4
    assert authentication._skip_quoted('x"a\\"b"', 1) == 7  # an escaped quote does not close it


def test_given_an_unterminated_quoted_string_when_skipped_then_none_is_returned() -> None:
    assert authentication._skip_quoted('"abc', 0) is None
    assert authentication._skip_quoted('"abc\\', 0) is None


def test_given_a_nested_comment_when_skipped_then_the_index_after_the_outer_close_is_returned() -> None:
    assert authentication._skip_comment("x(a(b)c)d", 1) == 8
    assert authentication._skip_comment("x(ab)", 1) == 5
    assert authentication._skip_comment("x(a\\)b)", 1) == 7  # an escaped parenthesis does not close it


def test_given_an_unterminated_comment_when_skipped_then_none_is_returned() -> None:
    assert authentication._skip_comment("(a(b)", 0) is None
    assert authentication._skip_comment("(ab\\", 0) is None


def test_given_comments_and_quotes_when_split_then_comments_become_spaces_and_quotes_are_opaque() -> None:
    assert authentication._split_results('a(b)c;d"x;y"e') == ["a c", 'd"_"e']
    assert authentication._split_results("a; b ;c") == ["a", " b ", "c"]
    assert authentication._split_results("a(x;y)b") == ["a b"]
    assert authentication._split_results("") == [""]


@pytest.mark.parametrize("header", ["a)b", "a(b", 'a"b', "a(b\\", "(a))"])
def test_given_an_ambiguous_header_when_split_then_none_is_returned(header: str) -> None:
    assert authentication._split_results(header) is None


def test_given_a_vouching_header_when_a_sender_is_on_a_list_then_its_kind_is_returned() -> None:
    header = f"{SERVER}; dmarc=pass header.from=google.test"
    assert _kind(header) is PinnedKind.GOOGLE_SECURITY
    assert _kind(header.replace("google.test", "app.test"), "code@app.test") is PinnedKind.SIGN_IN_CODE
    assert _kind(header.replace("google.test", "mm.test"), "code@MM.test") is PinnedKind.SIGN_IN_CODE


def test_given_a_sender_off_the_lists_or_no_header_then_there_is_no_kind() -> None:
    assert _kind(f"{SERVER}; dmarc=pass header.from=other.test", "a@other.test") is None
    assert pinned_kind([], "a@google.test", SENDERS) is None


@pytest.mark.parametrize("result", ["fail", "reject", "none", "temperror", "permerror", "PASSED"])
def test_given_a_dmarc_result_other_than_pass_then_the_mail_is_not_pinned(result: str) -> None:
    assert _kind(f"{SERVER}; dmarc={result} header.from=google.test") is None


def test_given_the_dmarc_result_in_capitals_then_it_still_counts_as_pass() -> None:
    assert _kind(f"{SERVER}; DMARC=PASS header.from=GOOGLE.test") is PinnedKind.GOOGLE_SECURITY


def test_given_a_header_from_domain_other_than_the_sender_then_the_mail_is_not_pinned() -> None:
    assert _kind(f"{SERVER}; dmarc=pass header.from=aaa.test") is None
    assert _kind(f"{SERVER}; dmarc=pass header.from=zzz.test") is None
    assert _kind(f"{SERVER}; dmarc=pass header.from=google.test header.from=google.test") is None
    assert _kind(f"{SERVER}; dmarc=pass") is None


def test_given_the_wrong_server_or_none_then_the_mail_is_not_pinned() -> None:
    assert _kind("evil.test; dmarc=pass header.from=google.test") is None
    assert _kind("; dmarc=pass header.from=google.test") is None
    assert _kind("MX.Google.COM 1; dmarc=pass header.from=google.test") is PinnedKind.GOOGLE_SECURITY


def test_given_two_dmarc_results_or_a_hidden_one_then_the_mail_is_not_pinned() -> None:
    assert _kind(f"{SERVER}; dmarc=pass header.from=google.test; dmarc=pass header.from=google.test") is None
    assert _kind(f'{SERVER}; dmarc=pass header.from=google.test; x="dmarc=fail"') is PinnedKind.GOOGLE_SECURITY
    assert _kind(f"{SERVER}; dmarc=pass header.from=google.test (dmarc=fail)") is PinnedKind.GOOGLE_SECURITY
    assert _kind(f"{SERVER}; x-dmarc=pass header.from=google.test") is None
    assert _kind(f"{SERVER}; spf=pass; dmarc=pass header.from=google.test") is PinnedKind.GOOGLE_SECURITY


def test_given_several_headers_then_only_the_topmost_counts() -> None:
    good = f"{SERVER}; dmarc=pass header.from=google.test"
    bad = f"{SERVER}; dmarc=fail header.from=google.test"
    assert pinned_kind([good, bad], "a@google.test", SENDERS) is PinnedKind.GOOGLE_SECURITY
    assert pinned_kind([bad, good], "a@google.test", SENDERS) is None


def test_given_an_unterminated_comment_in_the_header_then_the_mail_is_not_pinned() -> None:
    assert _kind(f"{SERVER}; dmarc=pass (header.from=google.test") is None


def test_given_the_value_objects_when_changed_then_they_are_frozen_and_slotted() -> None:
    assert not hasattr(SENDERS, "__dict__")
    with pytest.raises(FrozenInstanceError):
        SENDERS.__setattr__("sign_in", frozenset())
    assert (PinnedKind.GOOGLE_SECURITY.value, PinnedKind.SIGN_IN_CODE.value) == ("google_security", "sign_in_code")
    assert authentication.GMAIL_AUTHSERV_ID == "mx.google.com"
