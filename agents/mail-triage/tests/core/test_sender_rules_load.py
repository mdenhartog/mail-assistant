"""U-label-structure-14, criterion 5 (AC-61): 100 categories with 100 senders each match within a time bound."""

from __future__ import annotations

import time

from app.core.judgement import ListedCategory
from app.core.sender_rules import RuleFiling, RuleSkipped, SenderRules
from category_policy.kinds import Kind
from category_policy.senders import SenderEntry

CATEGORIES = 100
SENDERS = 100
BOUND_SECONDS = 1.0  # generous: the batch below takes a small fraction of it on a slow runner
AUTH = "mx.google.com; spf=pass; dmarc=pass header.from={domain}"


def _entry(category: int, index: int) -> SenderEntry:
    if index % 2:
        return SenderEntry(f"person{index}@shop{category}.nl")
    return SenderEntry(f"partner{index}-{category}.nl", subdomains=True)


def _rules() -> SenderRules:
    return SenderRules(
        tuple(
            ListedCategory(
                f"00000000-0000-0000-0000-{category:012d}",
                f"Category {category}",
                "load",
                Kind.TOPIC,
                False,
                tuple(_entry(category, index) for index in range(SENDERS)),
            )
            for category in range(CATEGORIES)
        )
    )


def test_given_100_categories_with_100_senders_when_building_and_matching_a_batch_then_it_stays_within_the_bound() -> (
    None
):
    started = time.perf_counter()
    rules = _rules()
    outcomes = []
    for category in range(0, CATEGORIES, 2):  # a listed address, a listed subdomain and a stranger for each
        address = f"person{category | 1}@shop{category}.nl"
        domain = f"partner{category & ~1}-{category}.nl"
        outcomes.append(rules.apply((AUTH.format(domain=address.rpartition("@")[2]),), address))
        outcomes.append(rules.apply((AUTH.format(domain=f"mail.{domain}"),), f"news@mail.{domain}"))
        outcomes.append(rules.apply((AUTH.format(domain="stranger.nl"),), "who@stranger.nl"))
    elapsed = time.perf_counter() - started

    assert elapsed < BOUND_SECONDS
    assert all(isinstance(o, RuleFiling) for o in outcomes[0::3])
    assert all(isinstance(o, RuleFiling) for o in outcomes[1::3])
    assert all(o is None for o in outcomes[2::3])


def test_given_the_large_list_when_the_sender_is_not_authenticated_then_the_rule_is_skipped_within_the_bound() -> None:
    rules = _rules()
    started = time.perf_counter()
    outcomes = [rules.apply((), f"person{c | 1}@shop{c}.nl") for c in range(0, CATEGORIES, 2)]
    elapsed = time.perf_counter() - started

    assert elapsed < BOUND_SECONDS
    assert all(isinstance(o, RuleSkipped) for o in outcomes)
