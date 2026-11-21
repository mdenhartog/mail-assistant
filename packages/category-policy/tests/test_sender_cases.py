"""The shared sender contract cases (AC-10 to AC-14, AC-61): the same file is run by the agent and by the api."""

import json
from pathlib import Path
from typing import Any

import pytest

from category_policy import (
    SENDER_RULES,
    SENDERS_PER_CATEGORY_MAX,
    Kind,
    SenderCategory,
    SenderEntry,
    build_matcher,
    parse_entry,
    validate_entries,
)

PACKAGE = Path(__file__).resolve().parents[1]
FILE: dict[str, Any] = json.loads((PACKAGE / "contract" / "sender_cases.json").read_text("utf-8"))


def _categories(case: dict[str, Any]) -> list[SenderCategory]:
    categories = [
        SenderCategory(
            name=c["name"],
            kind=Kind(c["kind"]),
            entries=tuple(SenderEntry(e["text"], e["subdomains"]) for e in c["entries"]),
        )
        for c in case["categories"]
    ]
    if "generate_entries" in case:
        extra = tuple(SenderEntry(f"s{i}@example.nl") for i in range(case["generate_entries"]))
        categories[0] = SenderCategory(categories[0].name, categories[0].kind, extra)
    return categories


@pytest.mark.parametrize("case", FILE["entry"], ids=[c["id"] for c in FILE["entry"]])
def test_given_an_entry_case_when_parsed_then_the_stored_form_matches_the_file(case: dict[str, Any]):
    text = "a" * 64 + ".nl" if case["text"] == "__label_64__.nl" else case["text"]

    parsed = parse_entry(text, case["subdomains"])

    assert (parsed.value if parsed else None) == case["value"]


@pytest.mark.parametrize("case", FILE["validate"], ids=[c["id"] for c in FILE["validate"]])
def test_given_a_validate_case_when_validated_then_the_problems_match_the_file(case: dict[str, Any]):
    problems = validate_entries(_categories(case))

    assert [[p.rule, p.index, p.position, p.other_index] for p in problems] == case["problems"]


@pytest.mark.parametrize("case", FILE["match"], ids=[c["id"] for c in FILE["match"]])
def test_given_a_match_case_when_matched_then_the_categories_match_the_file(case: dict[str, Any]):
    found = build_matcher(_categories(case))(case["from"])

    topic = found.topic.category if found and found.topic else None
    extra = found.extra.category if found and found.extra else None
    assert (topic, extra) == (case["topic"], case["extra"])


def test_given_the_sender_cases_when_listed_then_ids_are_unique_per_section():
    for section in ("entry", "validate", "match"):
        ids = [c["id"] for c in FILE[section]]
        assert ids
        assert len(ids) == len(set(ids))


def test_given_the_sender_rules_when_compared_with_the_cases_then_every_rule_has_a_refusing_case():
    covered = {p[0] for c in FILE["validate"] for p in c["problems"]}

    assert len(SENDER_RULES) == len(set(SENDER_RULES))
    assert set(SENDER_RULES) == covered
    assert any(c.get("generate_entries") == SENDERS_PER_CATEGORY_MAX for c in FILE["validate"])
