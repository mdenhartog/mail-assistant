"""The shared contract cases (AC-2, AC-8): the same file is run by the agent and by the api."""

import json
from pathlib import Path
from typing import Any

import pytest

from category_policy import MAX_CATEGORIES, RULES, Category, normalise_name, validate_category, validate_list

PACKAGE = Path(__file__).resolve().parents[1]
FILE: dict[str, Any] = json.loads((PACKAGE / "contract" / "category_cases.json").read_text("utf-8"))


def _fill(description: str) -> str:
    if description.startswith("__") and description.endswith("__"):
        return "d" * int(description.strip("_"))
    return description


@pytest.mark.parametrize("case", FILE["normalise"], ids=[c["id"] for c in FILE["normalise"]])
def test_given_a_normalise_case_when_normalised_then_the_expected_name_comes_out(case: dict[str, Any]):
    assert normalise_name(case["raw"]) == case["expected"]


@pytest.mark.parametrize("case", FILE["category"], ids=[c["id"] for c in FILE["category"]])
def test_given_a_category_case_when_validated_then_the_rules_match_the_file(case: dict[str, Any]):
    problems = validate_category(case["name"], _fill(case["description"]), case["existing"], case["labels"])

    assert [p.rule for p in problems] == case["rules"]


@pytest.mark.parametrize("case", FILE["list"], ids=[c["id"] for c in FILE["list"]])
def test_given_a_list_case_when_validated_then_the_problems_match_the_file(case: dict[str, Any]):
    if "generate" in case:
        categories = [Category(name=f"Category {i}", description="x") for i in range(case["generate"])]
    else:
        categories = [Category(name=c["name"], description=c["description"]) for c in case["categories"]]

    problems = validate_list(categories, case["labels"])

    assert [[p.index, p.rule] for p in problems] == case["problems"]


def test_given_the_contract_cases_when_listed_then_ids_are_unique_per_section():
    for section in ("normalise", "category", "list"):
        ids = [c["id"] for c in FILE[section]]
        assert len(ids) == len(set(ids))


def test_given_the_exported_rules_when_compared_with_the_cases_then_every_rule_has_a_refusing_case():
    covered = {r for c in FILE["category"] for r in c["rules"]} | {p[1] for c in FILE["list"] for p in c["problems"]}

    assert len(RULES) == len(set(RULES))
    assert set(RULES) == covered


def test_given_the_cap_when_read_then_it_is_fifty():
    assert MAX_CATEGORIES == 50
