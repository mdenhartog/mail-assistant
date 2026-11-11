"""U-web-settings-17, unit level: the pure rules of the request-code endpoint."""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import pytest

from app.auth import request_code_rules
from app.auth.request_code_rules import origin_allowed, same_key, username_key, wait_seconds

T0 = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)
COOLDOWN = timedelta(seconds=60)
CAP = 5
ORIGIN = "https://settings.example.test"


def _sent(*offsets: int) -> list[datetime]:
    return [T0 + timedelta(seconds=offset) for offset in offsets]


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        (ORIGIN, True),
        (None, False),
        ("", False),
        ("https://evil.example", False),
        (ORIGIN + "/", False),
        (ORIGIN.upper(), False),
        ("http://settings.example.test", False),
        (ORIGIN + ".evil.example", False),
        ("null", False),
    ],
)
def test_given_an_origin_when_checked_then_only_the_exact_public_origin_passes(
    origin: str | None, expected: bool
) -> None:
    assert origin_allowed(origin, ORIGIN) is expected


def test_given_an_empty_public_origin_when_checked_then_nothing_passes() -> None:
    assert origin_allowed("", "") is False
    assert origin_allowed(None, "") is False


def test_given_a_username_when_keyed_then_it_is_the_full_hmac_sha256_hex() -> None:
    expected = hmac.new(b"k" * 32, b"test-user", hashlib.sha256).hexdigest()

    assert username_key(b"k" * 32, "test-user") == expected
    assert len(expected) == 64


def test_given_other_keys_or_names_when_keyed_then_the_result_differs() -> None:
    base = username_key(b"k" * 32, "test-user")

    assert username_key(b"j" * 32, "test-user") != base
    assert username_key(b"k" * 32, "other-user") != base
    assert username_key(b"k" * 32, "test-user") == base


def test_given_two_keys_when_compared_then_they_are_equal_only_when_identical() -> None:
    first = username_key(b"k" * 32, "a")

    assert same_key(first, first) is True
    assert same_key(first, username_key(b"k" * 32, "b")) is False
    assert same_key(first, first[:-1] + ("0" if first[-1] != "0" else "1")) is False


def test_given_the_comparison_when_made_then_it_uses_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bytes, bytes]] = []

    def spy(first: bytes, second: bytes) -> bool:
        calls.append((first, second))
        return True

    monkeypatch.setattr(request_code_rules.hmac, "compare_digest", spy)

    assert same_key("aa", "bb") is True
    assert calls == [(b"aa", b"bb")]


def test_given_no_earlier_request_when_asked_then_no_wait() -> None:
    assert wait_seconds(None, [], T0, COOLDOWN, CAP) == 0


def test_given_a_request_59_and_60_seconds_ago_when_asked_then_one_second_then_none() -> None:
    assert wait_seconds(T0, [], T0 + timedelta(seconds=59), COOLDOWN, CAP) == 1
    assert wait_seconds(T0, [], T0 + timedelta(seconds=60), COOLDOWN, CAP) == 0


def test_given_a_request_just_now_when_asked_then_the_whole_cooldown() -> None:
    assert wait_seconds(T0, [], T0, COOLDOWN, CAP) == 60
    assert wait_seconds(T0, [], T0 + timedelta(milliseconds=500), COOLDOWN, CAP) == 60


def test_given_five_sent_codes_when_asked_then_the_wait_is_until_the_oldest_leaves_the_hour() -> None:
    sent = _sent(0, 60, 120, 180, 240)
    now = T0 + timedelta(seconds=300)

    assert wait_seconds(T0 + timedelta(seconds=240), sent, now, COOLDOWN, CAP) == 3300


def test_given_five_sent_codes_when_asked_at_59m59_and_60m01_then_one_second_then_none() -> None:
    sent = _sent(0, 60, 120, 180, 240)
    last = T0 + timedelta(seconds=240)

    assert wait_seconds(last, sent, T0 + timedelta(seconds=3599), COOLDOWN, CAP) == 1
    assert wait_seconds(last, sent, T0 + timedelta(seconds=3600), COOLDOWN, CAP) == 0
    assert wait_seconds(last, sent, T0 + timedelta(seconds=3601), COOLDOWN, CAP) == 0


def test_given_four_sent_codes_when_asked_then_the_cap_is_not_reached() -> None:
    sent = _sent(0, 60, 120, 180)

    assert wait_seconds(T0 + timedelta(seconds=180), sent, T0 + timedelta(seconds=300), COOLDOWN, CAP) == 0


def test_given_more_sent_codes_than_the_cap_when_asked_then_enough_must_leave_the_hour() -> None:
    sent = _sent(0, 60, 120, 180, 240, 300, 360)
    now = T0 + timedelta(seconds=400)

    # seven in the hour, cap five: three must fall out, the third oldest (120) leaves at 3720.
    assert wait_seconds(T0 + timedelta(seconds=360), sent, now, COOLDOWN, CAP) == 3320


def test_given_unsorted_sent_codes_when_asked_then_the_order_does_not_matter() -> None:
    sent = _sent(240, 0, 180, 60, 120)

    assert wait_seconds(T0 + timedelta(seconds=240), sent, T0 + timedelta(seconds=300), COOLDOWN, CAP) == 3300


def test_given_the_cooldown_is_longer_than_the_cap_wait_when_asked_then_the_longer_wait_counts() -> None:
    sent = _sent(0, 60, 120, 180, 240)
    now = T0 + timedelta(seconds=3599)

    assert wait_seconds(T0 + timedelta(seconds=3598), sent, now, COOLDOWN, CAP) == 59


def test_given_sent_codes_older_than_an_hour_when_asked_then_they_do_not_count() -> None:
    sent = _sent(0, 1, 2, 3, 4)

    assert wait_seconds(None, sent, T0 + timedelta(seconds=3604), COOLDOWN, CAP) == 0


def test_given_a_naive_time_when_asked_then_it_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        wait_seconds(None, [], datetime(2026, 3, 1, 14, 0, 0), COOLDOWN, CAP)  # noqa: DTZ001
