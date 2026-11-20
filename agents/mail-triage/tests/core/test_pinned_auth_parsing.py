"""RED-005: the Authentication-Results header is parsed as RFC 8601 says, so injected text cannot forge a pass."""

from __future__ import annotations

import random

import pytest

from app.core.pinned import PinnedKind, PinnedSenders, pinned_kind

ALLOW = PinnedSenders(google_security=frozenset({"accounts.google.com"}), sign_in=frozenset({"mail.example.test"}))
SENDER = "no-reply@accounts.google.com"
DOMAIN = "accounts.google.com"
ALPHABET = list('()"\\;= a.:/@-<>x\t')


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _comment_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")


def _random_text(rng: random.Random) -> str:
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 24)))


def test_given_an_injected_local_part_when_checked_then_the_forged_pass_is_not_trusted() -> None:
    injected = f'spf=fail smtp.mailfrom="a);dmarc=pass header.from={DOMAIN};x=("@evil.example'
    header = f"mx.google.com; {injected}; dmarc=fail header.from={DOMAIN}"

    assert pinned_kind((header,), SENDER, ALLOW) is None


def test_given_an_unquoted_injection_that_fakes_a_second_dmarc_when_checked_then_it_fails_closed() -> None:
    header = f"mx.google.com; spf=fail smtp.mailfrom=a); dmarc=pass header.from={DOMAIN}; x=(; dmarc=fail"

    assert pinned_kind((header,), SENDER, ALLOW) is None


def test_given_the_injection_before_a_failing_dmarc_when_checked_then_the_real_fail_is_not_hidden() -> None:
    header = f'mx.google.com; spf=pass smtp.mailfrom="a(";dmarc=pass header.from={DOMAIN};x=")"; dmarc=fail'

    assert pinned_kind((header,), SENDER, ALLOW) is None


@pytest.mark.parametrize(
    "header",
    [
        f"mx.google.com; dmarc=pass header.from={DOMAIN}; dmarc=pass header.from={DOMAIN}",  # two results: ambiguous
        f"mx.google.com; dmarc=pass header.from={DOMAIN}; dmarc=fail header.from={DOMAIN}",
        f"mx.google.com; dmarc=fail header.from={DOMAIN}; dmarc=pass header.from={DOMAIN}",
        f"mx.google.com; dmarc=pass header.from={DOMAIN} (unclosed",  # unterminated comment
        f'mx.google.com; spf=pass smtp.mailfrom="unclosed; dmarc=pass header.from={DOMAIN}',  # unterminated quote
        f"mx.google.com; dmarc=pass header.from={DOMAIN}) ",  # stray closing parenthesis
        f"mx.google.com; spf=pass dmarc=pass header.from={DOMAIN}",  # a dmarc result that is not its own part
        f"mx.google.com; dmarc=pass header.from={DOMAIN} header.from=evil.example",
    ],
)
def test_given_an_ambiguous_header_when_checked_then_it_fails_closed(header: str) -> None:
    assert pinned_kind((header,), SENDER, ALLOW) is None


@pytest.mark.parametrize(
    "header",
    [
        f"mx.google.com; spf=pass (domain of a@x designates 1.2.3.4); dmarc=pass (p=REJECT) header.from={DOMAIN}",
        f"mx.google.com (nested (comment (deep))); dmarc=pass header.from={DOMAIN}",
        f"mx.google.com 1; dmarc=pass header.from={DOMAIN}",
        f'mx.google.com; spf=pass smtp.mailfrom="a;b(c"@x.example; dmarc=pass header.from={DOMAIN}',
        rf"mx.google.com; spf=pass (a \) b); dmarc=pass header.from={DOMAIN}",
        f"mx.google.com;\r\n\tdmarc=pass\r\n\theader.from={DOMAIN}",
    ],
)
def test_given_an_honest_header_when_checked_then_it_still_passes(header: str) -> None:
    assert pinned_kind((header,), SENDER, ALLOW) is PinnedKind.GOOGLE_SECURITY


def test_given_any_quoted_mailfrom_before_a_failing_dmarc_when_checked_then_it_is_never_pinned() -> None:
    rng = random.Random(8601)  # noqa: S311 - a fixed seed, not security
    for _ in range(500):
        mailfrom = _quote(_random_text(rng))
        header = f"mx.google.com; spf=fail smtp.mailfrom={mailfrom}@evil.example; dmarc=fail header.from={DOMAIN}"
        assert pinned_kind((header,), SENDER, ALLOW) is None, header


def test_given_any_quoted_mailfrom_before_a_passing_dmarc_when_checked_then_it_is_still_pinned() -> None:
    rng = random.Random(8602)  # noqa: S311 - a fixed seed, not security
    for _ in range(500):
        mailfrom = _quote(_random_text(rng))
        header = f"mx.google.com; spf=pass smtp.mailfrom={mailfrom}@x.example; dmarc=pass header.from={DOMAIN}"
        assert pinned_kind((header,), SENDER, ALLOW) is PinnedKind.GOOGLE_SECURITY, header


def test_given_any_escaped_comment_text_when_checked_then_the_verdict_is_unchanged() -> None:
    rng = random.Random(8603)  # noqa: S311 - a fixed seed, not security
    for _ in range(500):
        comment = f"({_comment_text(_random_text(rng))})"
        good = f"mx.google.com; spf=pass {comment}; dmarc=pass {comment} header.from={DOMAIN}"
        bad = f"mx.google.com; spf=pass {comment}; dmarc=fail {comment} header.from={DOMAIN}"
        assert pinned_kind((good,), SENDER, ALLOW) is PinnedKind.GOOGLE_SECURITY, good
        assert pinned_kind((bad,), SENDER, ALLOW) is None, bad
