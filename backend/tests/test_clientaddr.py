"""U-web-settings-24, -51, -64: the client address of a request, pure rules (unit level)."""

import pytest

from app.clientaddr import UNKNOWN_CLIENT, client_key, ipv6_prefix48

PROXIES = ["10.42.0.0/16"]
PROXY = "10.42.1.7"


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
    assert client_key("fd00::1", "2001:DB8:0:1:0:0:0:1", ["fd00::/8"], 1) == "2001:db8:0:1::/64"
    assert client_key("2001:DB8:0:2:0:0:0:2", None, [], 1) == "2001:db8:0:2::/64"


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


def test_given_a_cidr_written_with_host_bits_when_keyed_then_it_still_trusts_the_network() -> None:
    assert client_key("10.42.1.7", "203.0.113.9", ["10.42.1.7/16"], 1) == "203.0.113.9"


def test_given_two_slash_64_networks_when_keyed_then_the_buckets_are_separate() -> None:
    first = client_key("2001:db8:0:1::5", None, [], 1)
    second = client_key("2001:db8:0:2::5", None, [], 1)

    assert first == "2001:db8:0:1::/64"
    assert second == "2001:db8:0:2::/64"
    assert first != second


def test_given_the_last_bit_of_the_64_prefix_when_keyed_then_it_splits_the_networks() -> None:
    assert client_key("2001:db8:0:0:ffff:ffff:ffff:ffff", None, [], 1) == "2001:db8::/64"
    assert client_key("2001:db8:0:1::", None, [], 1) == "2001:db8:0:1::/64"


def test_given_a_forwarded_ipv6_address_when_keyed_then_it_is_the_slash_64_of_that_address() -> None:
    assert client_key("fd00::1", "9::9, 2001:db8:0:3:aaaa::1", ["fd00::/8"], 1) == "2001:db8:0:3::/64"


def test_given_an_ipv4_address_when_keyed_then_it_stays_itself() -> None:
    assert client_key("203.0.113.9", None, [], 1) == "203.0.113.9"
    assert client_key("::ffff:203.0.113.9", None, [], 1) == "203.0.113.9"


def test_given_a_trusted_ipv6_peer_without_a_header_when_keyed_then_the_peer_slash_64_is_the_key() -> None:
    assert client_key("fd00:0:0:5::7", None, ["fd00::/8"], 1) == "fd00:0:0:5::/64"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("2001:db8:0:1::/64", "2001:db8::/48"),
        ("2001:db8:7:ffff::/64", "2001:db8:7::/48"),
        ("2001:db8:8:1::/64", "2001:db8:8::/48"),
        ("203.0.113.9", None),
        ("unknown", None),
        ("not an address", None),
        ("2001:db8::/48", None),
        ("2001:db8:0:1::5", None),
    ],
)
def test_given_a_client_key_when_its_slash_48_is_asked_then_only_an_ipv6_slash_64_has_one(
    key: str, expected: str | None
) -> None:
    assert ipv6_prefix48(key) == expected
