"""Sender entries and the pure matcher (INT-008, C-4, D15, ADR-0054).

An entry is a full address or a domain, compared as lower-case A-labels. Entries are plain strings, never patterns:
the matcher is two dictionary lookups plus one probe per label of the sender's domain, so no entry can make a match
slower. Everything here is total: bad input gives ``None`` or a reported problem, never an exception.
"""

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from email.utils import getaddresses

from category_policy.kinds import Kind
from category_policy.refused_domains import is_refused_domain

SENDERS_PER_CATEGORY_MAX = 100
SENDER_RULES = ("sender_invalid", "sender_too_many", "sender_duplicate", "sender_refused_domain")

_DOMAIN_MAX = 253
_LOCAL_MAX = 64
_FROM_MAX = 998
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_LOCAL = re.compile(r"[a-z0-9._%+'=&~^-]+")


@dataclass(frozen=True, slots=True)
class SenderEntry:
    """A sender entry as the user writes it.

    Attributes:
        text: A full address or a domain.
        subdomains: Only for a domain: also match its subdomains.
    """

    text: str
    subdomains: bool = False


@dataclass(frozen=True, slots=True)
class SenderCategory:
    """The part of a category the sender rules need."""

    name: str
    kind: Kind
    entries: tuple[SenderEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedEntry:
    """A valid entry in its stored form (lower-case A-labels)."""

    value: str
    is_domain: bool
    subdomains: bool


@dataclass(frozen=True, slots=True)
class SenderProblem:
    """One refusal of a sender entry.

    Attributes:
        rule: One of ``SENDER_RULES``.
        index: Position of the category in the list.
        position: Position of the entry in the category, or None for a rule about the whole category.
        other_index: For ``sender_duplicate``, the category that has the entry already (equal to ``index`` when the
            entry is repeated inside one category).
        entry: For ``sender_duplicate``, the entry in its stored form.
    """

    rule: str
    index: int
    position: int | None = None
    other_index: int | None = None
    entry: str | None = None


@dataclass(frozen=True, slots=True)
class Hit:
    """The category that listed the matching entry."""

    category: str
    entry: str


@dataclass(frozen=True, slots=True)
class Match:
    """What a sender matches: at most one topic and at most one extra label, each by its longest entry."""

    topic: Hit | None
    extra: Hit | None


type Matcher = Callable[[str | None], Match | None]


def _a_label_domain(text: str) -> str | None:
    """Return the lower-case A-label form of a domain, or None when it cannot be one.

    Text that the IDNA mapping would change (full-width letters, ``ß``) is refused rather than silently folded.
    """
    lowered = text.lower()
    try:
        encoded = lowered.encode("idna").decode("ascii")
        decoded = encoded.encode("ascii").decode("idna")
    except UnicodeError:
        return None
    if not lowered.isascii() and decoded != unicodedata.normalize("NFC", lowered):
        return None
    labels = encoded.split(".")
    if len(labels) < 2 or len(encoded) > _DOMAIN_MAX:  # noqa: PLR2004
        return None
    return encoded if all(_LABEL.fullmatch(label) for label in labels) else None


def _address(text: str) -> str | None:
    """Return ``local@domain`` in stored form, or None."""
    local, separator, domain = text.partition("@")
    if not separator or "@" in domain:
        return None
    local = local.lower()
    a_label = _a_label_domain(domain)
    if a_label is None or len(local) > _LOCAL_MAX or not _LOCAL.fullmatch(local):
        return None
    return f"{local}@{a_label}"


def parse_entry(text: str, subdomains: bool) -> ParsedEntry | None:
    """Parse a sender entry into its stored form.

    Args:
        text: A full address or a domain; surrounding white space is ignored.
        subdomains: The opt-in to match subdomains; only a domain may have it.

    Returns:
        The entry, or None when it is not a valid address or domain (patterns, spaces, a bare name and similar).
    """
    cleaned = text.strip()
    if "@" in cleaned:
        value = None if subdomains else _address(cleaned)
        return None if value is None else ParsedEntry(value, is_domain=False, subdomains=False)
    domain = _a_label_domain(cleaned)
    return None if domain is None else ParsedEntry(domain, is_domain=True, subdomains=subdomains)


def _from_address(header: str | None) -> str | None:
    """Return the single address of a ``From`` value in stored form, or None for none, several or unparsable."""
    if not header or len(header) > _FROM_MAX:
        return None
    if header.count("<") != header.count(">"):
        return None
    found = getaddresses([header])
    if len(found) != 1:
        return None
    return _address(found[0][1].strip())


def _suffixes(domain: str) -> list[str]:
    labels = domain.split(".")
    return [".".join(labels[i:]) for i in range(len(labels))]


def _by_kind(categories: Sequence[SenderCategory], kind: Kind) -> tuple[dict[str, Hit], dict[str, tuple[Hit, bool]]]:
    addresses: dict[str, Hit] = {}
    domains: dict[str, tuple[Hit, bool]] = {}
    for category in categories:
        if category.kind is not kind:
            continue
        for entry in category.entries:
            parsed = parse_entry(entry.text, entry.subdomains)
            if parsed is None:
                continue
            hit = Hit(category.name, parsed.value)
            if parsed.is_domain:
                domains.setdefault(parsed.value, (hit, parsed.subdomains))
            else:
                addresses.setdefault(parsed.value, hit)
    return addresses, domains


def _longest(address: str, addresses: dict[str, Hit], domains: dict[str, tuple[Hit, bool]]) -> Hit | None:
    if address in addresses:
        return addresses[address]
    domain = address.rpartition("@")[2]
    for suffix in _suffixes(domain):
        found = domains.get(suffix)
        if found is not None and (suffix == domain or found[1]):
            return found[0]
    return None


def build_matcher(categories: Sequence[SenderCategory]) -> Matcher:
    """Build the matcher once per list version.

    The exact address beats a domain; among domains the longest one wins; a domain entry matches a subdomain only
    with ``subdomains`` and at a dot boundary. Invalid entries are ignored (they are refused on save). A topic and
    an extra label are matched independently.

    Args:
        categories: The categories with their sender entries.

    Returns:
        A pure function from a ``From`` header value to the match, or None when nothing matches. A missing, several
        or unparsable ``From`` matches nothing.
    """
    topic_addresses, topic_domains = _by_kind(categories, Kind.TOPIC)
    extra_addresses, extra_domains = _by_kind(categories, Kind.EXTRA)

    def match(from_header: str | None) -> Match | None:
        address = _from_address(from_header)
        if address is None:
            return None
        topic = _longest(address, topic_addresses, topic_domains)
        extra = _longest(address, extra_addresses, extra_domains)
        return None if topic is None and extra is None else Match(topic, extra)

    return match


def _entry_problems(index: int, category: SenderCategory, seen: dict[tuple[Kind, str], int]) -> list[SenderProblem]:
    problems: list[SenderProblem] = []
    for position, entry in enumerate(category.entries):
        parsed = parse_entry(entry.text, entry.subdomains)
        if parsed is None:
            problems.append(SenderProblem("sender_invalid", index, position))
        elif parsed.is_domain and is_refused_domain(parsed.value):
            problems.append(SenderProblem("sender_refused_domain", index, position))
        elif (category.kind, parsed.value) in seen:
            other = seen[category.kind, parsed.value]
            problems.append(SenderProblem("sender_duplicate", index, position, other, parsed.value))
        else:
            seen[category.kind, parsed.value] = index
    return problems


def validate_entries(categories: Sequence[SenderCategory]) -> list[SenderProblem]:
    """Check every sender entry of a list.

    At most 100 entries per category, every entry valid, no domain entry for a refused domain, and an entry in at
    most one topic category and one extra-label category (a repeat inside one category counts).

    Args:
        categories: The categories in list order.

    Returns:
        The problems in list order, or an empty list.
    """
    problems: list[SenderProblem] = []
    seen: dict[tuple[Kind, str], int] = {}
    for index, category in enumerate(categories):
        if len(category.entries) > SENDERS_PER_CATEGORY_MAX:
            problems.append(SenderProblem("sender_too_many", index))
        problems.extend(_entry_problems(index, category, seen))
    return problems
