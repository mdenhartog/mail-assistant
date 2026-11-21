"""Sender entries, the matcher and the refused domains (INT-008, C-4, D15, AC-10 to AC-14, AC-61)."""

import time

import pytest

from category_policy import (
    MAX_CATEGORIES,
    REFUSED_DOMAINS,
    SENDERS_PER_CATEGORY_MAX,
    Kind,
    SenderCategory,
    SenderEntry,
    build_matcher,
    is_refused_domain,
    parse_entry,
    validate_entries,
)


def cat(name: str, *entries: str | tuple[str, bool], kind: Kind = Kind.TOPIC) -> SenderCategory:
    return SenderCategory(
        name=name,
        kind=kind,
        entries=tuple(SenderEntry(e, False) if isinstance(e, str) else SenderEntry(*e) for e in entries),
    )


def topic_of(categories: list[SenderCategory], sender: str | None) -> str | None:
    found = build_matcher(categories)(sender)
    return found.topic.category if found and found.topic else None


# Criterion 1: the longest match wins.
def test_given_an_address_entry_and_a_domain_entry_when_both_match_then_the_address_wins():
    categories = [cat("Energy", "example.nl"), cat("Billing", "info@example.nl")]

    assert topic_of(categories, "info@example.nl") == "Billing"
    assert topic_of(categories, "other@example.nl") == "Energy"


def test_given_two_domain_entries_when_a_subdomain_sender_matches_both_then_the_longer_wins():
    categories = [cat("Wide", ("example.nl", True)), cat("Narrow", ("shop.example.nl", True))]

    assert topic_of(categories, "a@shop.example.nl") == "Narrow"
    assert topic_of(categories, "a@x.shop.example.nl") == "Narrow"
    assert topic_of(categories, "a@mail.example.nl") == "Wide"


def test_given_a_topic_entry_and_an_extra_entry_when_matched_then_both_are_reported_separately():
    categories = [cat("Energy", "example.nl"), cat("Invoices", "info@example.nl", kind=Kind.EXTRA)]

    found = build_matcher(categories)("info@example.nl")

    assert found is not None
    assert found.topic is not None
    assert (found.topic.category, found.topic.entry) == ("Energy", "example.nl")
    assert found.extra is not None
    assert (found.extra.category, found.extra.entry) == ("Invoices", "info@example.nl")


def test_given_an_extra_only_match_when_matched_then_the_topic_is_empty():
    found = build_matcher([cat("Invoices", "example.nl", kind=Kind.EXTRA)])("a@example.nl")

    assert found is not None
    assert found.topic is None
    assert found.extra is not None
    assert found.extra.category == "Invoices"


# Criterion 2: subdomains only on opt-in and at a dot boundary.
def test_given_a_domain_entry_without_the_opt_in_when_a_subdomain_sender_is_matched_then_nothing_matches():
    categories = [cat("Energy", "example.nl")]

    assert topic_of(categories, "a@example.nl") == "Energy"
    assert topic_of(categories, "a@mail.example.nl") is None


def test_given_the_opt_in_when_matched_then_subdomains_match_at_a_dot_boundary_only():
    categories = [cat("Energy", ("example.nl", True))]

    assert topic_of(categories, "a@mail.example.nl") == "Energy"
    assert topic_of(categories, "a@a.b.example.nl") == "Energy"
    assert topic_of(categories, "a@evilexample.nl") is None


def test_given_the_opt_in_on_an_address_entry_when_parsed_then_it_is_refused():
    assert parse_entry("a@example.nl", True) is None


def test_given_entries_when_parsed_then_they_are_lower_case_a_labels():
    domain = parse_entry("  Bücher.Example.NL ", True)
    address = parse_entry("Info@Example.NL", False)

    assert domain is not None
    assert (domain.value, domain.is_domain, domain.subdomains) == ("xn--bcher-kva.example.nl", True, True)
    assert address is not None
    assert (address.value, address.is_domain, address.subdomains) == ("info@example.nl", False, False)


# Criterion 3: look-alikes and bad From headers match nothing.
@pytest.mark.parametrize(
    "sender",
    [
        "a@evil-example.nl",
        "a@example.nl.evil.com",
        "a@exаmple.nl",  # Cyrillic a
        "a@ｅxample.nl",  # full-width e
        "a@xn--xample-9ua.nl",
        "a@example.nl.",
        "a@example.nl\r\nBcc: x@y.nl",
        None,
        "",
        "a@example.nl, b@example.nl",
        "Name <a@example.nl>, <b@example.nl>",
        "not an address",
        "a@@example.nl",
        "<a@example.nl",
        "a@",
        "@example.nl",
    ],
)
def test_given_a_look_alike_or_a_bad_from_when_matched_against_the_domain_then_nothing_matches(sender: str | None):
    assert build_matcher([cat("Energy", ("example.nl", True))])(sender) is None


def test_given_a_display_name_with_a_listed_address_when_the_real_address_differs_then_nothing_matches():
    match = build_matcher([cat("Energy", "example.nl")])

    assert match('"a@example.nl" <a@evil.com>') is None
    assert match("Energy Co <a@example.nl>") is not None


def test_given_an_idn_sender_when_the_entry_is_the_same_label_then_it_matches_in_either_form():
    match = build_matcher([cat("Books", "bücher.nl")])

    assert match("a@bücher.nl") is not None
    assert match("a@xn--bcher-kva.nl") is not None
    assert match("a@BÜCHER.nl") is not None


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "*.example.nl",
        "*@example.nl",
        "example.*",
        "example",
        ".example.nl",
        "a..b.nl",
        "ex ample.nl",
        "a@b@c.nl",
        "-a.nl",
        "a-.nl",
        "x" * 64 + ".nl",
        "a@example",
        "re:^a.*$",
        "exаmple.nl\u200b",
        "xn--.nl",
        "xn--a-.nl",
    ],
)
def test_given_a_pattern_or_a_malformed_entry_when_parsed_then_it_is_refused(text: str):
    assert parse_entry(text, False) is None


# Criterion 4: an entry in at most one topic and one extra category.
def test_given_the_same_entry_in_two_topics_when_validated_then_it_is_refused_naming_both():
    categories = [cat("Energy", "Example.NL"), cat("Housing", "x@y.nl"), cat("Billing", "example.nl")]

    problems = validate_entries(categories)

    assert [(p.rule, p.index, p.other_index, p.entry) for p in problems] == [("sender_duplicate", 2, 0, "example.nl")]


def test_given_a_punycode_equal_entry_in_two_extras_when_validated_then_it_is_refused():
    categories = [
        cat("A", "bücher.nl", kind=Kind.EXTRA),
        cat("B", "xn--bcher-kva.nl", kind=Kind.EXTRA),
    ]

    assert [(p.rule, p.index, p.other_index) for p in validate_entries(categories)] == [("sender_duplicate", 1, 0)]


def test_given_the_same_entry_in_a_topic_and_an_extra_when_validated_then_it_is_accepted():
    categories = [cat("Energy", "example.nl"), cat("Invoices", "example.nl", kind=Kind.EXTRA)]

    assert validate_entries(categories) == []


def test_given_a_repeated_entry_inside_one_category_when_validated_then_it_is_refused():
    problems = validate_entries([cat("Energy", "example.nl", "EXAMPLE.nl")])

    assert [(p.rule, p.index, p.other_index, p.position) for p in problems] == [("sender_duplicate", 0, 0, 1)]


def test_given_a_domain_and_an_address_on_it_when_validated_then_they_are_different_entries():
    assert validate_entries([cat("A", "example.nl"), cat("B", "info@example.nl")]) == []


def test_given_an_invalid_entry_when_validated_then_the_position_is_reported():
    problems = validate_entries([cat("A", "example.nl", "*.example.nl")])

    assert [(p.rule, p.index, p.position) for p in problems] == [("sender_invalid", 0, 1)]


def test_given_more_than_the_limit_of_entries_when_validated_then_the_category_is_refused():
    entries = [f"s{i}@example.nl" for i in range(SENDERS_PER_CATEGORY_MAX + 1)]

    problems = validate_entries([cat("A", *entries)])

    assert [(p.rule, p.index) for p in problems] == [("sender_too_many", 0)]
    assert validate_entries([cat("A", *entries[:SENDERS_PER_CATEGORY_MAX])]) == []


# Criterion 5: refused domains.
@pytest.mark.parametrize(
    "domain",
    [
        "gmail.com",
        "GMAIL.com",
        "outlook.com",
        "yahoo.com",
        "icloud.com",
        "proton.me",
        "amazonses.com",
        "sendgrid.net",
        "onmicrosoft.com",
        "googlegroups.com",
        "mailchimpapp.net",
        "tenant.onmicrosoft.com",
        "eu-west-1.amazonses.com",
    ],
)
def test_given_a_domain_entry_for_a_refused_domain_when_validated_then_it_is_refused(domain: str):
    problems = validate_entries([cat("A", (domain, False))])

    assert [(p.rule, p.position) for p in problems] == [("sender_refused_domain", 0)]


def test_given_a_full_address_on_a_refused_domain_when_validated_then_it_is_accepted_and_matches():
    categories = [cat("Family", "oma@gmail.com")]

    assert validate_entries(categories) == []
    assert topic_of(categories, "oma@gmail.com") == "Family"
    assert topic_of(categories, "other@gmail.com") is None


def test_given_a_domain_that_only_ends_in_a_refused_name_when_validated_then_it_is_accepted():
    assert validate_entries([cat("A", "notgmail.com", "gmail.com.nl")]) == []
    assert is_refused_domain("gmail.com") is True
    assert is_refused_domain("a.gmail.com") is True
    assert is_refused_domain("notgmail.com") is False


def test_given_the_refused_lists_when_inspected_then_every_name_is_a_canonical_domain():
    assert len(REFUSED_DOMAINS) > 50
    for name in REFUSED_DOMAINS:
        entry = parse_entry(name, False)
        assert entry is not None
        assert entry.value == name


# Criterion 6: bounded matching.
def test_given_100_categories_of_100_entries_when_built_and_used_then_matching_stays_within_a_bound():
    categories = [
        cat(f"Category {i}", *[f"s{j}@d{i}-{j}.example.nl" if j % 2 else f"d{i}-{j}.example.nl" for j in range(100)])
        for i in range(MAX_CATEGORIES)
    ]
    assert validate_entries(categories) == []

    start = time.perf_counter()
    match = build_matcher(categories)
    build_seconds = time.perf_counter() - start
    start = time.perf_counter()
    for _ in range(1000):
        assert match("nobody@unknown.example.org") is None
        assert match("s1@d3-1.example.nl") is not None
    per_match = (time.perf_counter() - start) / 2000

    assert build_seconds < 5
    assert per_match < 0.005
