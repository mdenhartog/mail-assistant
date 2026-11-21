"""The shared contract cases (AC-1, AC-2, AC-6, AC-42): the same file is run by the agent and by the api."""

import json
from pathlib import Path
from typing import Any

import pytest

from category_policy import (
    RULES,
    Category,
    at_or_above,
    confidence_pct,
    label_for,
    normalise_name,
    validate_archive_label,
    validate_category,
    validate_instructions,
    validate_list,
)

PACKAGE = Path(__file__).resolve().parents[1]
FILE: dict[str, Any] = json.loads((PACKAGE / "contract" / "category_cases.json").read_text("utf-8"))
LABEL_LEN_PREFIX = "__label_len_"


def _fill(description: str) -> str:
    if description.startswith("__") and description.endswith("__"):
        return "d" * int(description.strip("_"))
    return description


def _name(name: str) -> str:
    """Expand ``__label_len_N__`` to a nested name whose Gmail label has N characters (segments of 40 letters)."""
    if not name.startswith(LABEL_LEN_PREFIX):
        return name
    length = int(name.removeprefix(LABEL_LEN_PREFIX).removesuffix("__")) - len("Assistant/")
    segments: list[str] = []
    while length > 0:
        take = min(40, length)
        segments.append("a" * take)
        length -= take + 1
    return "/".join(segments)


@pytest.mark.parametrize("case", FILE["normalise"], ids=[c["id"] for c in FILE["normalise"]])
def test_given_a_normalise_case_when_normalised_then_the_expected_name_comes_out(case: dict[str, Any]):
    assert normalise_name(case["raw"]) == case["expected"]


@pytest.mark.parametrize("case", FILE["label"], ids=[c["id"] for c in FILE["label"]])
def test_given_a_label_case_when_mapped_then_the_label_is_the_expected_one(case: dict[str, Any]):
    assert label_for(case["name"]) == case["expected"]


@pytest.mark.parametrize("case", FILE["category"], ids=[c["id"] for c in FILE["category"]])
def test_given_a_category_case_when_validated_then_the_rules_match_the_file(case: dict[str, Any]):
    problems = validate_category(
        _name(case["name"]), _fill(case["description"]), case["existing"], case["labels"], case["adoptable"]
    )

    assert [p.rule for p in problems] == case["rules"]


@pytest.mark.parametrize("case", FILE["list"], ids=[c["id"] for c in FILE["list"]])
def test_given_a_list_case_when_validated_then_the_problems_match_the_file(case: dict[str, Any]):
    if "generate" in case:
        categories = [Category(name=f"Category {i}", description="x") for i in range(case["generate"])]
    else:
        categories = [Category(name=c["name"], description=c["description"]) for c in case["categories"]]

    problems = validate_list(categories, case["labels"], case["adoptable"])

    assert [[p.index, p.rule] for p in problems] == case["problems"]


@pytest.mark.parametrize("case", FILE["instructions"], ids=[c["id"] for c in FILE["instructions"]])
def test_given_an_instructions_case_when_validated_then_the_rules_match_the_file(case: dict[str, Any]):
    problems = validate_instructions("i" * case["length"])

    assert [p.rule for p in problems] == case["rules"]


@pytest.mark.parametrize("case", FILE["archive"], ids=[c["id"] for c in FILE["archive"]])
def test_given_an_archive_case_when_validated_then_the_rules_match_the_file(case: dict[str, Any]):
    name = "a" * int(case["name"][6:-2]) if case["name"].startswith("__len_") else case["name"]
    categories = [Category(name=n, description="x") for n in case["categories"]]

    problems = validate_archive_label(name, categories)

    assert [p.rule for p in problems] == case["rules"]
    assert all(p.field == "archive_label" for p in problems)


@pytest.mark.parametrize("case", FILE["confidence"], ids=[c["id"] for c in FILE["confidence"]])
def test_given_a_confidence_case_when_converted_and_compared_then_the_file_decides(case: dict[str, Any]):
    pct = confidence_pct(case["confidence"])

    assert pct == case["pct"]
    assert at_or_above(pct, case["threshold"]) is case["at_or_above"]


def test_given_the_contract_cases_when_listed_then_ids_are_unique_per_section():
    sections = [key for key, value in FILE.items() if isinstance(value, list)]
    assert sections
    for section in sections:
        ids = [c["id"] for c in FILE[section]]
        assert len(ids) == len(set(ids))


def test_given_the_exported_rules_when_compared_with_the_cases_then_every_rule_has_a_refusing_case():
    covered = (
        {r for c in FILE["category"] for r in c["rules"]}
        | {p[1] for c in FILE["list"] for p in c["problems"]}
        | {r for c in FILE["instructions"] for r in c["rules"]}
        | {r for c in FILE["archive"] for r in c["rules"]}
    )

    assert len(RULES) == len(set(RULES))
    assert set(RULES) == covered
