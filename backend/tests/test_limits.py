"""U-web-settings-24: the pure rules of the request limits and of the client address (unit level)."""

import pytest

from app.clientaddr import UNKNOWN_CLIENT, client_key
from app.limits import FixedWindowLimiter, retry_after, window_key

T0 = 1_772_373_600.0  # 2026-03-01 14:00:00 UTC, a whole minute
PROXIES = ["10.42.0.0/16"]
PROXY = "10.42.1.7"


# ---- window_key and retry_after (criterion 9) ----


@pytest.mark.parametrize(("offset", "expected"), [(59.9, 0), (60.0, 1), (60.1, 1)])
def test_given_a_time_around_the_minute_boundary_when_keyed_then_0_1_1(offset: float, expected: int) -> None:
    assert window_key(offset) == expected


def test_given_a_whole_minute_when_keyed_then_it_is_the_minute_count() -> None:
    assert window_key(T0) == int(T0) // 60
    assert window_key(T0 + 59.9) == int(T0) // 60
    assert window_key(T0 + 60.0) == int(T0) // 60 + 1


def test_given_another_window_length_when_keyed_then_it_is_used() -> None:
    assert window_key(25.0, 10) == 2
    assert window_key(29.9, 10) == 2
    assert window_key(30.0, 10) == 3


@pytest.mark.parametrize(
    ("offset", "expected"),
    [(0.0, 60), (0.5, 60), (1.0, 59), (30.0, 30), (59.0, 1), (59.9, 1)],
)
def test_given_a_moment_in_a_window_when_retry_after_is_asked_then_whole_seconds_to_the_next_window(
    offset: float, expected: int
) -> None:
    assert retry_after(T0 + offset) == expected


def test_given_another_window_length_when_retry_after_is_asked_then_it_is_used() -> None:
    assert retry_after(T0 + 3.0, 10) == 7


# ---- the limiter (criteria 1, 2, 6, 7, 8) ----


def test_given_the_limit_when_one_more_arrives_then_it_is_refused_with_the_wait_to_the_next_window() -> None:
    limiter = FixedWindowLimiter(limit=3, window_seconds=60)

    decisions = [limiter.hit("1.2.3.4", "signin", T0 + 10) for _ in range(4)]

    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert decisions[3].retry_after == 50
    assert decisions[2].retry_after == 50


def test_given_a_refused_flood_when_hit_again_then_only_the_first_refusal_is_flagged() -> None:
    limiter = FixedWindowLimiter(limit=2, window_seconds=60)

    decisions = [limiter.hit("1.2.3.4", "api", T0) for _ in range(6)]

    assert [d.first_refusal for d in decisions] == [False, False, True, False, False, False]


def test_given_the_last_second_of_a_window_when_the_next_window_starts_then_the_count_restarts() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60)

    assert limiter.hit("c", "signin", T0 + 59.9).allowed
    assert not limiter.hit("c", "signin", T0 + 59.9).allowed
    assert limiter.hit("c", "signin", T0 + 60.0).allowed
    assert not limiter.hit("c", "signin", T0 + 60.1).allowed


def test_given_a_refusal_in_a_window_when_the_next_window_refuses_again_then_it_is_flagged_again() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60)
    for _ in range(3):
        limiter.hit("c", "signin", T0)

    again = [limiter.hit("c", "signin", T0 + 61) for _ in range(3)]

    assert [d.first_refusal for d in again] == [False, True, False]


def test_given_two_buckets_and_two_clients_when_one_is_exhausted_then_the_others_are_unaffected() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60)
    assert limiter.hit("a", "api", T0).allowed
    assert not limiter.hit("a", "api", T0).allowed

    assert limiter.hit("a", "signin", T0).allowed
    assert limiter.hit("b", "api", T0).allowed


def test_given_different_limits_when_hit_then_each_limiter_uses_its_own() -> None:
    low = FixedWindowLimiter(limit=1, window_seconds=60)
    high = FixedWindowLimiter(limit=2, window_seconds=60)

    assert [low.hit("c", "api", T0).allowed for _ in range(2)] == [True, False]
    assert [high.hit("c", "api", T0).allowed for _ in range(3)] == [True, True, False]


def test_given_a_shorter_window_when_the_time_passes_it_then_the_count_restarts() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=10)

    assert limiter.hit("c", "api", T0).allowed
    assert not limiter.hit("c", "api", T0 + 9.9).allowed
    assert limiter.hit("c", "api", T0 + 10.0).allowed


def test_given_many_clients_and_windows_when_counted_then_old_windows_go_and_the_size_is_bounded() -> None:
    limiter = FixedWindowLimiter(limit=5, window_seconds=60)

    for minute in range(50):
        for client in range(20):
            limiter.hit(f"10.0.0.{client}", "api", T0 + 60 * minute)

    assert limiter.tracked_windows() == 2
    assert limiter.tracked_entries() == 2 * 20


def test_given_a_previous_window_when_the_next_one_is_counted_then_the_previous_one_is_still_held() -> None:
    limiter = FixedWindowLimiter(limit=5, window_seconds=60)
    limiter.hit("a", "api", T0)
    limiter.hit("a", "api", T0 + 60)

    assert limiter.tracked_windows() == 2
    assert limiter.tracked_entries() == 2

    limiter.hit("a", "api", T0 + 120)

    assert limiter.tracked_windows() == 2
    assert limiter.tracked_entries() == 2


def test_given_a_fresh_limiter_when_asked_then_nothing_is_tracked() -> None:
    limiter = FixedWindowLimiter(limit=5, window_seconds=60)

    assert limiter.tracked_windows() == 0
    assert limiter.tracked_entries() == 0


# ---- the client address (criterion 4) ----


def test_given_the_last_trusted_proxy_appended_the_client_when_keyed_then_it_is_the_key() -> None:
    assert client_key(PROXY, "spoof, 203.0.113.9", PROXIES, 1) == "203.0.113.9"


def test_given_a_spoofed_leftmost_value_when_keyed_then_it_never_opens_a_fresh_bucket() -> None:
    first = client_key(PROXY, "1.1.1.1, 203.0.113.9", PROXIES, 1)
    second = client_key(PROXY, "2.2.2.2, 203.0.113.9", PROXIES, 1)

    assert first == second == "203.0.113.9"


def test_given_two_trusted_hops_when_keyed_then_the_entry_two_from_the_right_is_the_client() -> None:
    assert client_key(PROXY, "9.9.9.9, 203.0.113.9, 10.42.3.3", PROXIES, 2) == "203.0.113.9"


def test_given_fewer_entries_than_hops_when_keyed_then_the_peer_is_the_key() -> None:
    assert client_key(PROXY, "203.0.113.9", PROXIES, 2) == PROXY


@pytest.mark.parametrize("header", [None, "", "   ", ",", "not-an-address", "203.0.113.9, nope"])
def test_given_no_usable_forwarded_entry_when_keyed_then_the_peer_is_the_key(header: str | None) -> None:
    assert client_key(PROXY, header, PROXIES, 1) == PROXY


def test_given_a_peer_outside_the_trusted_cidrs_when_keyed_then_its_own_address_and_the_header_is_ignored() -> None:
    assert client_key("198.51.100.4", "203.0.113.9", PROXIES, 1) == "198.51.100.4"


def test_given_no_trusted_cidrs_when_keyed_then_the_peer_is_the_key() -> None:
    assert client_key(PROXY, "203.0.113.9", [], 1) == PROXY


def test_given_a_peer_in_the_second_of_two_cidrs_when_keyed_then_it_is_trusted() -> None:
    assert client_key("192.168.5.5", "203.0.113.9", ["10.0.0.0/8", "192.168.0.0/16"], 1) == "203.0.113.9"


def test_given_no_peer_when_keyed_then_it_is_unknown() -> None:
    assert client_key(None, "203.0.113.9", PROXIES, 1) == UNKNOWN_CLIENT == "unknown"


def test_given_a_peer_that_is_not_an_address_when_keyed_then_it_is_kept_as_it_is() -> None:
    assert client_key("testclient", "203.0.113.9", PROXIES, 1) == "testclient"


def test_given_ipv6_addresses_when_keyed_then_they_are_written_in_one_canonical_form() -> None:
    assert client_key("fd00::1", "2001:DB8:0:0:0:0:0:1", ["fd00::/8"], 1) == "2001:db8::1"
    assert client_key("2001:DB8:0:0:0:0:0:2", None, [], 1) == "2001:db8::2"


def test_given_an_ipv4_mapped_peer_when_keyed_then_it_matches_the_ipv4_cidr() -> None:
    assert client_key("::ffff:10.42.1.7", "203.0.113.9", PROXIES, 1) == "203.0.113.9"
    assert client_key("::ffff:198.51.100.4", "203.0.113.9", PROXIES, 1) == "198.51.100.4"


def test_given_a_forwarded_ipv4_mapped_address_when_keyed_then_it_is_the_ipv4_address() -> None:
    assert client_key(PROXY, "::ffff:203.0.113.9", PROXIES, 1) == "203.0.113.9"


def test_given_hops_below_one_when_keyed_then_the_peer_is_the_key() -> None:
    assert client_key(PROXY, "203.0.113.9", PROXIES, 0) == PROXY
    assert client_key(PROXY, "203.0.113.9", PROXIES, -1) == PROXY


def test_given_spaces_around_the_entries_when_keyed_then_they_are_trimmed() -> None:
    assert client_key(PROXY, "  1.1.1.1 ,   203.0.113.9  ", PROXIES, 1) == "203.0.113.9"


def test_given_odd_and_even_windows_when_retry_after_is_asked_then_it_counts_to_the_next_window_start() -> None:
    assert retry_after(T0 + 60 + 20.0) == 40
    assert retry_after(T0 + 120 + 20.0) == 40
    assert retry_after(T0 + 180 + 45.0) == 15


def test_given_a_gap_of_several_windows_when_counted_then_everything_older_than_two_windows_is_dropped() -> None:
    limiter = FixedWindowLimiter(limit=5, window_seconds=60)
    limiter.hit("a", "api", T0)
    limiter.hit("a", "api", T0 + 60)

    limiter.hit("a", "api", T0 + 60 * 10)

    assert limiter.tracked_windows() == 1
    assert limiter.tracked_entries() == 1


def test_given_a_cidr_written_with_host_bits_when_keyed_then_it_still_trusts_the_network() -> None:
    assert client_key("10.42.1.7", "203.0.113.9", ["10.42.1.7/16"], 1) == "203.0.113.9"
