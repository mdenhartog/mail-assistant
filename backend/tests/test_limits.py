"""U-web-settings-24, -51, -64: the pure rules of the request limits (unit level); the address is in test_clientaddr."""

import dataclasses

import pytest

from app.clientaddr import client_key
from app.limits import FixedWindowLimiter, retry_after, surplus, window_key

T0 = 1_772_373_600.0  # 2026-03-01 14:00:00 UTC, a whole minute


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


def test_given_a_decision_when_it_is_changed_then_it_is_refused() -> None:
    decision = FixedWindowLimiter(limit=1, window_seconds=60, max_counters=10).hit("a", "api", T0)

    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.allowed = False  # type: ignore[misc]  # frozen on purpose


def test_given_a_limit_above_the_small_int_cache_when_exceeded_then_the_first_refusal_is_the_next_hit() -> None:
    limiter = FixedWindowLimiter(limit=300, window_seconds=60, max_counters=10)

    decisions = [limiter.hit("a", "api", T0) for _ in range(302)]

    assert [n for n, d in enumerate(decisions, start=1) if d.first_refusal] == [301]
    assert [n for n, d in enumerate(decisions, start=1) if not d.allowed] == [301, 302]


@pytest.mark.parametrize(("offset", "expected"), [(0.0, 60), (59.999, 1), (60.0, 60), (60.001, 60)])
def test_given_a_moment_at_a_window_edge_when_retry_after_is_asked_then_it_is_between_1_and_the_window_length(
    offset: float, expected: int
) -> None:
    assert retry_after(T0 + offset) == expected


def test_given_the_limit_when_one_more_arrives_then_it_is_refused_with_the_wait_to_the_next_window() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=3, window_seconds=60)

    decisions = [limiter.hit("1.2.3.4", "signin", T0 + 10) for _ in range(4)]

    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert decisions[3].retry_after == 50
    assert decisions[2].retry_after == 50


def test_given_a_refused_flood_when_hit_again_then_only_the_first_refusal_is_flagged() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=2, window_seconds=60)

    decisions = [limiter.hit("1.2.3.4", "api", T0) for _ in range(6)]

    assert [d.first_refusal for d in decisions] == [False, False, True, False, False, False]


def test_given_the_last_second_of_a_window_when_the_next_window_starts_then_the_count_restarts() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=1, window_seconds=60)

    assert limiter.hit("c", "signin", T0 + 59.9).allowed
    assert not limiter.hit("c", "signin", T0 + 59.9).allowed
    assert limiter.hit("c", "signin", T0 + 60.0).allowed
    assert not limiter.hit("c", "signin", T0 + 60.1).allowed


def test_given_a_refusal_in_a_window_when_the_next_window_refuses_again_then_it_is_flagged_again() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=1, window_seconds=60)
    for _ in range(3):
        limiter.hit("c", "signin", T0)

    again = [limiter.hit("c", "signin", T0 + 61) for _ in range(3)]

    assert [d.first_refusal for d in again] == [False, True, False]


def test_given_two_buckets_and_two_clients_when_one_is_exhausted_then_the_others_are_unaffected() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=1, window_seconds=60)
    assert limiter.hit("a", "api", T0).allowed
    assert not limiter.hit("a", "api", T0).allowed

    assert limiter.hit("a", "signin", T0).allowed
    assert limiter.hit("b", "api", T0).allowed


def test_given_different_limits_when_hit_then_each_limiter_uses_its_own() -> None:
    low = FixedWindowLimiter(max_counters=1000, limit=1, window_seconds=60)
    high = FixedWindowLimiter(max_counters=1000, limit=2, window_seconds=60)

    assert [low.hit("c", "api", T0).allowed for _ in range(2)] == [True, False]
    assert [high.hit("c", "api", T0).allowed for _ in range(3)] == [True, True, False]


def test_given_a_shorter_window_when_the_time_passes_it_then_the_count_restarts() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=1, window_seconds=10)

    assert limiter.hit("c", "api", T0).allowed
    assert not limiter.hit("c", "api", T0 + 9.9).allowed
    assert limiter.hit("c", "api", T0 + 10.0).allowed


def test_given_many_clients_and_windows_when_counted_then_old_windows_go_and_the_size_is_bounded() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=5, window_seconds=60)

    for minute in range(50):
        for client in range(20):
            limiter.hit(f"10.0.0.{client}", "api", T0 + 60 * minute)

    assert limiter.tracked_windows() == 2
    assert limiter.tracked_entries() == 2 * 20


def test_given_a_previous_window_when_the_next_one_is_counted_then_the_previous_one_is_still_held() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=5, window_seconds=60)
    limiter.hit("a", "api", T0)
    limiter.hit("a", "api", T0 + 60)

    assert limiter.tracked_windows() == 2
    assert limiter.tracked_entries() == 2

    limiter.hit("a", "api", T0 + 120)

    assert limiter.tracked_windows() == 2
    assert limiter.tracked_entries() == 2


def test_given_a_fresh_limiter_when_asked_then_nothing_is_tracked() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=5, window_seconds=60)

    assert limiter.tracked_windows() == 0
    assert limiter.tracked_entries() == 0


# ---- the client address (criterion 4) ----


def test_given_odd_and_even_windows_when_retry_after_is_asked_then_it_counts_to_the_next_window_start() -> None:
    assert retry_after(T0 + 60 + 20.0) == 40
    assert retry_after(T0 + 120 + 20.0) == 40
    assert retry_after(T0 + 180 + 45.0) == 15


def test_given_a_gap_of_several_windows_when_counted_then_everything_older_than_two_windows_is_dropped() -> None:
    limiter = FixedWindowLimiter(max_counters=1000, limit=5, window_seconds=60)
    limiter.hit("a", "api", T0)
    limiter.hit("a", "api", T0 + 60)

    limiter.hit("a", "api", T0 + 60 * 10)

    assert limiter.tracked_windows() == 1
    assert limiter.tracked_entries() == 1


# ---- U-web-settings-51: IPv6 per /64 (criterion 2) ----


def test_given_31_addresses_of_one_slash_64_when_keyed_and_counted_then_the_31st_is_refused() -> None:
    limiter = FixedWindowLimiter(limit=30, window_seconds=60, max_counters=1000)

    decisions = [limiter.hit(client_key(f"2001:db8:0:1:{n:x}::{n:x}", None, [], 1), "signin", T0) for n in range(1, 32)]

    assert [d.allowed for d in decisions] == [True] * 30 + [False]


# ---- U-web-settings-51, rebuilt in U-web-settings-64: the bound evicts the oldest keys, it never refuses a key ----


def test_given_the_bound_is_reached_when_a_new_key_arrives_then_it_is_allowed_and_the_oldest_key_is_evicted() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60, max_counters=3)
    for name in ("a", "b", "c"):
        assert limiter.hit(name, "api", T0).allowed

    new = limiter.hit("d", "api", T0 + 10)

    assert new.allowed
    assert not new.first_refusal
    assert limiter.tracked_entries() == 3
    assert limiter.hit("a", "api", T0 + 11).allowed  # the oldest was evicted: its count starts again
    assert not limiter.hit("c", "api", T0 + 11).allowed  # a younger key kept its count


def test_given_the_bound_is_reached_when_a_known_key_hits_again_then_it_is_still_counted_and_nothing_is_evicted() -> (
    None
):
    limiter = FixedWindowLimiter(limit=2, window_seconds=60, max_counters=2)
    limiter.hit("a", "api", T0)
    limiter.hit("b", "api", T0)

    again = [limiter.hit("a", "api", T0) for _ in range(2)]

    assert [d.allowed for d in again] == [True, False]
    assert [d.first_refusal for d in again] == [False, True]
    assert not limiter.hit("a", "api", T0).allowed
    assert limiter.tracked_entries() == 2
    assert limiter.hit("b", "api", T0).allowed
    assert not limiter.hit("b", "api", T0).allowed  # b still held its first count


def test_given_one_client_with_two_buckets_when_counted_then_each_pair_is_one_counter() -> None:
    limiter = FixedWindowLimiter(limit=5, window_seconds=60, max_counters=2)

    assert limiter.hit("a", "api", T0).allowed
    assert limiter.hit("a", "signin", T0).allowed
    assert limiter.tracked_entries() == 2
    assert limiter.hit("a", "other", T0).allowed
    assert limiter.tracked_entries() == 2


def test_given_a_full_window_when_the_next_window_starts_then_new_keys_are_counted_again() -> None:
    limiter = FixedWindowLimiter(limit=5, window_seconds=60, max_counters=1)
    assert limiter.hit("a", "api", T0).allowed

    assert limiter.hit("b", "api", T0 + 60).allowed
    assert limiter.hit("a", "api", T0 + 60).allowed
    assert limiter.tracked_entries() == 2  # one counter in each of the two windows held, as the bound says per window


def test_given_a_flood_of_distinct_keys_when_counted_then_memory_stays_at_the_bound() -> None:
    limiter = FixedWindowLimiter(limit=5, window_seconds=60, max_counters=50)

    decisions = [limiter.hit(f"k{n}", "api", T0 + n * 0.01) for n in range(5000)]

    assert all(d.allowed for d in decisions)
    assert limiter.tracked_entries() == 50


def test_given_10000_keys_from_one_slash_48_when_the_owner_elsewhere_hits_then_it_keeps_its_count() -> None:
    limiter = FixedWindowLimiter(limit=2, window_seconds=60, max_counters=10000)
    owner = "2001:db8:1:1::/64"
    assert limiter.hit(owner, "signin", T0).allowed

    flood = [limiter.hit(f"2001:db8:0:{n:x}::/64", "signin", T0 + 1) for n in range(10000)]
    second = limiter.hit(owner, "signin", T0 + 2)
    third = limiter.hit(owner, "signin", T0 + 2)

    assert all(d.allowed for d in flood)
    assert second.allowed
    assert not third.allowed  # the owner's counter was not evicted by the flood
    assert limiter.tracked_entries() <= 10000 // 10 + 1


def test_given_10000_keys_from_the_owners_own_slash_48_when_the_owner_hits_then_it_is_never_refused() -> None:
    limiter = FixedWindowLimiter(limit=2, window_seconds=60, max_counters=10000)
    owner = "2001:db8:0:ffff::/64"
    limiter.hit(owner, "signin", T0)

    for n in range(10000):
        limiter.hit(f"2001:db8:0:{n:x}::/64", "signin", T0 + 1)

    assert limiter.hit(owner, "signin", T0 + 2).allowed


def test_given_the_prefix_bound_when_a_new_key_of_a_full_slash_48_arrives_then_the_oldest_of_that_prefix_goes() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60, max_counters=100)  # 10 counters per /48
    other = "2001:db8:9:1::/64"
    limiter.hit(other, "api", T0)
    for n in range(10):
        limiter.hit(f"2001:db8:0:{n:x}::/64", "api", T0)

    assert limiter.hit("2001:db8:0:a::/64", "api", T0).allowed

    assert limiter.tracked_entries() == 11
    assert limiter.hit("2001:db8:0:0::/64", "api", T0).allowed  # the oldest of the prefix was evicted
    assert not limiter.hit("2001:db8:0:5::/64", "api", T0).allowed  # a younger one kept its count
    assert not limiter.hit(other, "api", T0).allowed  # another prefix is untouched


@pytest.mark.parametrize(
    ("bound", "per_prefix"), [(1, 1), (5, 1), (10, 1), (11, 2), (20, 2), (21, 3), (25, 3), (30, 3), (100, 10)]
)
def test_given_a_bound_when_one_slash_48_floods_then_it_holds_a_tenth_of_it_rounded_up(
    bound: int, per_prefix: int
) -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60, max_counters=bound)

    for n in range(per_prefix + 3):
        limiter.hit(f"2001:db8:0:{n:x}::/64", "api", T0)

    assert limiter.tracked_entries() == per_prefix


@pytest.mark.parametrize(
    ("held", "bound", "expected"),
    [(0, 3, 0), (1, 3, 0), (2, 3, 0), (3, 3, 1), (4, 3, 2), (5, 3, 3), (6, 3, 4), (1, 1, 1)],
)
def test_given_the_held_counters_and_the_bound_when_the_surplus_is_asked_then_it_is_how_many_must_go_for_one_more(
    held: int, bound: int, expected: int
) -> None:
    assert surplus(held, bound) == expected


def test_given_room_under_both_bounds_when_new_keys_arrive_then_nothing_is_evicted() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60, max_counters=100)  # 10 counters per /48
    keys = [f"2001:db8:0:{n:x}::/64" for n in range(9)] + ["203.0.113.1", "203.0.113.2"]
    for key in keys:
        limiter.hit(key, "api", T0)

    assert limiter.tracked_entries() == 11
    assert all(not limiter.hit(key, "api", T0).allowed for key in keys)


def test_given_a_tiny_bound_when_an_ipv6_key_arrives_then_the_prefix_bound_is_at_least_one() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60, max_counters=5)

    assert limiter.hit("2001:db8:0:1::/64", "api", T0).allowed
    assert not limiter.hit("2001:db8:0:1::/64", "api", T0).allowed
    assert limiter.hit("2001:db8:0:2::/64", "api", T0).allowed
    assert limiter.tracked_entries() == 1


def test_given_ipv4_keys_when_counted_then_the_prefix_bound_does_not_apply() -> None:
    limiter = FixedWindowLimiter(limit=5, window_seconds=60, max_counters=100)

    for n in range(30):
        limiter.hit(f"203.0.113.{n}", "api", T0)

    assert limiter.tracked_entries() == 30


# ---- U-web-settings-64: the /48 of an IPv6 key ----
