"""Property-based tests on sender entries and the matcher (no entry makes matching slower or wrong)."""

from hypothesis import given
from hypothesis import strategies as st

from category_policy import Kind, SenderCategory, SenderEntry, build_matcher, parse_entry, validate_entries

LABELS = st.sampled_from(["a", "b", "shop", "mail", "example", "evil"])
DOMAINS = st.builds(".".join, st.lists(LABELS, min_size=1, max_size=4).map(lambda ls: [*ls, "nl"]))
ADDRESSES = st.builds("{}@{}".format, st.sampled_from(["x", "info", "me"]), DOMAINS)
ENTRIES = st.one_of(
    st.builds(SenderEntry, DOMAINS, st.booleans()),
    st.builds(SenderEntry, ADDRESSES, st.just(False)),
)
CATEGORIES = st.lists(
    st.builds(
        SenderCategory,
        name=st.text(min_size=1, max_size=5),
        kind=st.sampled_from(Kind),
        entries=st.lists(ENTRIES, max_size=6).map(tuple),
    ),
    max_size=6,
)


def _reference(categories: list[SenderCategory], kind: Kind, sender: str) -> str | None:
    """Brute-force longest match over every entry, by the written rules."""
    domain = sender.partition("@")[2]
    best: tuple[int, str] | None = None
    for category in categories:
        if category.kind is not kind:
            continue
        for entry in category.entries:
            parsed = parse_entry(entry.text, entry.subdomains)
            if parsed is None:
                continue
            if parsed.is_domain:
                hit = domain == parsed.value or (parsed.subdomains and domain.endswith("." + parsed.value))
            else:
                hit = sender == parsed.value
            rank = len(parsed.value) + (1000 if not parsed.is_domain else 0)
            if hit and (best is None or rank > best[0]):
                best = (rank, category.name)
    return best[1] if best else None


@given(categories=CATEGORIES, sender=ADDRESSES)
def test_given_any_entries_when_matched_then_the_result_equals_the_brute_force_longest_match(
    categories: list[SenderCategory], sender: str
):
    if validate_entries(categories):
        return  # a refused list has no defined match (the same entry twice)

    found = build_matcher(categories)(sender)

    for kind in Kind:
        hit = (found.topic if kind is Kind.TOPIC else found.extra) if found else None
        expected = _reference(categories, kind, sender)
        assert (hit.category if hit else None) == expected


@given(categories=CATEGORIES, extra=CATEGORIES, sender=ADDRESSES)
def test_given_more_entries_in_a_valid_list_when_matched_then_a_match_never_disappears(
    categories: list[SenderCategory], extra: list[SenderCategory], sender: str
):
    before = build_matcher(categories)(sender)
    after = build_matcher([*categories, *extra])(sender)

    if before is not None:
        assert after is not None


@given(sender=st.text(max_size=200))
def test_given_any_text_as_from_when_matched_then_it_never_raises(sender: str):
    build_matcher([SenderCategory("A", Kind.TOPIC, (SenderEntry("example.nl", True),))])(sender)


@given(text=st.text(max_size=80), subdomains=st.booleans())
def test_given_any_text_when_parsed_then_it_never_raises_and_the_result_is_stable(text: str, subdomains: bool):
    parsed = parse_entry(text, subdomains)

    if parsed is not None:
        assert parse_entry(parsed.value, parsed.subdomains) == parsed
