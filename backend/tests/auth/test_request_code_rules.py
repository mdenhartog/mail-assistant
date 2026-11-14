"""U-web-settings-17, unit level: the pure rules of the request-code endpoint."""

import dataclasses
import hashlib
import hmac
from datetime import UTC, datetime, timedelta, tzinfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.auth import request_code_rules
from app.auth.request_code_rules import (
    RequestFacts,
    RequestLimits,
    client_hash,
    normalize_username,
    origin_allowed,
    request_wait,
    same_key,
    username_key,
    wait_until_below,
)

T0 = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)
COOLDOWN = timedelta(seconds=60)
CAP = 5
ORIGIN = "https://settings.example.test"


def _sent(*offsets: int) -> list[datetime]:
    return [T0 + timedelta(seconds=offset) for offset in offsets]


def _limits(**overrides: int | timedelta) -> RequestLimits:
    values: dict[str, int | timedelta] = {
        "cooldown": COOLDOWN,
        "codes_per_hour": CAP,
        "live_per_username": 3,
        "open_per_client": 10,
        "requests_per_client_per_hour": 20,
    }
    values.update(overrides)
    return RequestLimits(**values)  # pyright: ignore[reportArgumentType]


def wait_seconds(
    last_requested_at: datetime | None, created: list[datetime], now: datetime, cooldown: timedelta, cap: int
) -> int:
    """The username rules alone: the cooldown from the newest request and the hourly cap over every created row."""
    facts = RequestFacts(
        username_created=created
        if last_requested_at is None or last_requested_at in created
        else [*created, last_requested_at],
        username_live=[],
        client_created=[],
        client_live=[],
    )
    return request_wait(facts, now, _limits(cooldown=cooldown, codes_per_hour=cap))


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
    sent = _sent(0, 60, 120, 180, 3598)
    now = T0 + timedelta(seconds=3599)

    assert wait_seconds(T0 + timedelta(seconds=3598), sent, now, COOLDOWN, CAP) == 59


def test_given_sent_codes_older_than_an_hour_when_asked_then_they_do_not_count() -> None:
    sent = _sent(0, 1, 2, 3, 4)

    assert wait_seconds(None, sent, T0 + timedelta(seconds=3604), COOLDOWN, CAP) == 0


def test_given_a_cap_of_one_and_one_sent_code_when_asked_then_the_wait_is_until_it_leaves_the_hour() -> None:
    assert wait_seconds(T0, _sent(0), T0 + timedelta(seconds=100), COOLDOWN, 1) == 3500


def test_given_a_naive_time_when_asked_then_it_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        wait_seconds(None, [], datetime(2026, 3, 1, 14, 0, 0), COOLDOWN, CAP)  # noqa: DTZ001


# ---- U-web-settings-53 ---------------------------------------------------------------------------------------------


def _facts(**overrides: list[datetime]) -> RequestFacts:
    values: dict[str, list[datetime]] = {
        "username_created": [],
        "username_live": [],
        "client_created": [],
        "client_live": [],
    }
    values.update(overrides)
    return RequestFacts(**values)


def _old_client_hash(key: bytes, client: str) -> str:
    return hmac.new(key, b"client:" + client.encode("utf-8"), hashlib.sha256).hexdigest()


def test_given_a_client_key_when_hashed_then_it_is_a_hmac_under_a_derived_subkey() -> None:
    subkey = hmac.new(b"k" * 32, b"client-key", hashlib.sha256).digest()
    expected = hmac.new(subkey, b"10.0.0.1", hashlib.sha256).hexdigest()

    assert client_hash(b"k" * 32, "10.0.0.1") == expected
    assert len(expected) == 64


def test_given_a_client_key_when_hashed_then_it_differs_from_the_old_formula() -> None:
    assert client_hash(b"k" * 32, "10.0.0.5") != _old_client_hash(b"k" * 32, "10.0.0.5")


def test_given_other_keys_or_clients_when_hashed_then_the_result_differs_and_is_not_the_username_key() -> None:
    base = client_hash(b"k" * 32, "10.0.0.1")

    assert client_hash(b"j" * 32, "10.0.0.1") != base
    assert client_hash(b"k" * 32, "10.0.0.2") != base
    assert client_hash(b"k" * 32, "10.0.0.1") == base
    assert username_key(b"k" * 32, "10.0.0.1") != base


@pytest.mark.parametrize("key", [b"k" * 32, b"j" * 32])
def test_given_a_username_typed_like_a_client_label_when_keyed_then_it_never_equals_the_client_digest(
    key: bytes,
) -> None:
    assert username_key(key, "client:10.0.0.5") != client_hash(key, "10.0.0.5")
    assert username_key(key, "10.0.0.5") != client_hash(key, "10.0.0.5")
    assert username_key(key, "client:10.0.0.5") == hmac.new(key, b"client:10.0.0.5", hashlib.sha256).hexdigest()


def test_given_fewer_held_than_the_limit_when_asked_then_no_wait() -> None:
    assert wait_until_below(_sent(100, 200), T0, 3) == 0
    assert wait_until_below([], T0, 1) == 0


def test_given_the_limit_reached_when_asked_then_the_wait_is_until_the_earliest_release() -> None:
    assert wait_until_below(_sent(600, 700, 800), T0 + timedelta(seconds=100), 3) == 500
    assert wait_until_below(_sent(800, 600, 700), T0 + timedelta(seconds=100), 3) == 500  # order does not matter


def test_given_more_held_than_the_limit_when_asked_then_enough_must_be_released() -> None:
    # four held, limit two: three must be released, the third earliest (800) frees the slot.
    assert wait_until_below(_sent(600, 700, 800, 900), T0 + timedelta(seconds=100), 2) == 700


def test_given_releases_in_the_past_when_asked_then_they_are_not_held() -> None:
    assert wait_until_below(_sent(50, 100, 700), T0 + timedelta(seconds=100), 2) == 0
    assert wait_until_below(_sent(101, 200), T0 + timedelta(seconds=100), 2) == 1


def test_given_a_release_part_of_a_second_away_when_asked_then_the_wait_rounds_up() -> None:
    assert wait_until_below([T0 + timedelta(seconds=10, milliseconds=1)], T0, 1) == 11


def test_given_a_naive_time_when_the_wait_is_asked_then_it_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        wait_until_below([datetime(2026, 3, 1, 14, 0, 0)], T0, 1)  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        wait_until_below([T0], datetime(2026, 3, 1, 14, 0, 0), 1)  # noqa: DTZ001


def test_given_no_facts_when_asked_then_no_wait() -> None:
    assert request_wait(_facts(), T0, _limits()) == 0


def test_given_live_requests_of_the_username_at_the_limit_when_asked_then_the_wait_is_the_earliest_expiry() -> None:
    facts = _facts(username_live=_sent(600, 650, 700))

    assert request_wait(facts, T0 + timedelta(seconds=200), _limits(live_per_username=3)) == 400
    assert request_wait(facts, T0 + timedelta(seconds=200), _limits(live_per_username=4)) == 0


def test_given_the_client_hourly_number_reached_when_asked_then_the_wait_is_until_the_oldest_leaves_the_hour() -> None:
    facts = _facts(client_created=_sent(0, 100, 200))
    now = T0 + timedelta(seconds=300)

    assert request_wait(facts, now, _limits(requests_per_client_per_hour=3)) == 3300
    assert request_wait(facts, now, _limits(requests_per_client_per_hour=4)) == 0


def test_given_the_client_open_number_reached_when_asked_then_the_wait_is_the_earliest_expiry() -> None:
    facts = _facts(client_live=_sent(600, 650))

    assert request_wait(facts, T0, _limits(open_per_client=2)) == 600
    assert request_wait(facts, T0, _limits(open_per_client=3)) == 0


def test_given_several_limits_when_asked_then_the_longest_wait_counts() -> None:
    facts = _facts(
        username_created=_sent(0),  # cooldown: 60
        username_live=_sent(600),  # live limit 1: 600
        client_live=_sent(700),  # open limit 1: 700
    )
    limits = _limits(live_per_username=1, open_per_client=1)

    assert request_wait(facts, T0, limits) == 700
    assert request_wait(facts, T0, _limits(live_per_username=1, open_per_client=9)) == 600
    assert request_wait(facts, T0, _limits(live_per_username=9, open_per_client=9)) == 60


def test_given_the_hourly_cap_of_the_username_and_the_client_when_asked_then_each_counts_from_created_at() -> None:
    username = _facts(username_created=_sent(0, 10, 20))
    client = _facts(client_created=_sent(0, 10, 20))
    now = T0 + timedelta(seconds=100)

    assert request_wait(username, now, _limits(codes_per_hour=3, cooldown=timedelta(0))) == 3500
    assert request_wait(client, now, _limits(requests_per_client_per_hour=3)) == 3500
    assert request_wait(username, now, _limits(codes_per_hour=4, cooldown=timedelta(0))) == 0


def test_given_an_equal_but_separate_origin_string_when_checked_then_it_passes() -> None:
    assert origin_allowed("".join(["https://settings", ".example.test"]), ORIGIN) is True


def test_given_a_release_exactly_now_when_asked_then_it_is_no_wait_and_does_not_hold_a_slot() -> None:
    now = T0 + timedelta(seconds=100)

    assert wait_until_below([now], now, 1) == 0
    assert wait_until_below([now, now + timedelta(seconds=7)], now, 1) == 7
    assert wait_until_below([now - timedelta(seconds=1), now + timedelta(seconds=7)], now, 2) == 0


def test_given_the_limits_and_facts_when_changed_then_they_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _limits().cooldown = timedelta(0)  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(dataclasses.FrozenInstanceError):
        _facts().username_created = []  # pyright: ignore[reportAttributeAccessIssue]


class _NoOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None


def test_given_a_time_with_a_zone_that_has_no_offset_when_asked_then_it_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        wait_until_below([T0], datetime(2026, 3, 1, 14, 0, 0, tzinfo=_NoOffset()), 1)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("marco", "marco"),
        ("Marco", "marco"),
        ("MARCO", "marco"),
        (" marco ", "marco"),
        ("\t marco\n", "marco"),
        ("\xa0marco\u3000", "marco"),  # no-break and ideographic spaces count as spaces
        ("ma rco", "ma rco"),  # inner spaces stay: only the ends are trimmed
        ("Stra\xdfe", "strasse"),  # sharp s folds to ss (casefold, not lower)
        ("".join(chr(0xFF21 + n) for n in (12, 0, 17, 2, 14)), "marco"),  # full-width letters fold (NFKC)
        ("\u0130", "i\u0307"),  # folds to i + combining dot, never a plain i
        ("user@example.test", "user@example.test"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_given_a_typed_username_when_normalised_then_ends_are_trimmed_and_case_and_width_are_folded(
    typed: str, expected: str
) -> None:
    assert normalize_username(typed) == expected


def test_given_plain_lowercase_names_when_normalised_then_nothing_changes() -> None:
    for name in ("marco", "test-user", "a.b_c-9", "x" * 64):
        assert normalize_username(name) == name


@given(st.text(max_size=80))
def test_given_any_text_when_normalised_twice_then_the_second_pass_changes_nothing(raw: str) -> None:
    once = normalize_username(raw)
    assert normalize_username(once) == once
    assert once == once.strip()


@given(st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=20))
def test_given_ascii_text_when_padded_or_recased_then_the_key_is_the_same(raw: str) -> None:
    key = b"k" * 32
    base = username_key(key, normalize_username(raw))
    assert username_key(key, normalize_username(f"  {raw.upper()}\t")) == base
    assert username_key(key, normalize_username(raw.lower())) == base


def test_given_an_email_address_when_normalised_then_it_is_not_the_username() -> None:
    assert normalize_username(" Marco@Example.Test ") != normalize_username("marco")
