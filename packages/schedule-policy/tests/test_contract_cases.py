"""The shared contract cases (AC-36): the same file is run by the agent's settings store and by web-settings."""

import json
import re
from datetime import time
from pathlib import Path
from typing import Any

import pytest

from schedule_policy.policy import TimePolicy, validate

PACKAGE = Path(__file__).resolve().parents[1]
CASES: list[dict[str, Any]] = json.loads((PACKAGE / "contract" / "settings_cases.json").read_text("utf-8"))["cases"]


def _policy(raw: dict[str, str]) -> TimePolicy:
    return TimePolicy(
        zone=raw["zone"],
        quiet_start=time.fromisoformat(raw["quiet_start"]),
        quiet_end=time.fromisoformat(raw["quiet_end"]),
        overview_at=time.fromisoformat(raw["overview_at"]),
        remind_at=time.fromisoformat(raw["remind_at"]),
    )


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_given_a_contract_case_when_validated_then_the_rules_match_the_file(case: dict[str, Any]):
    assert [problem.rule for problem in validate(_policy(case["policy"]))] == case["rules"]


def test_given_the_contract_cases_when_listed_then_ids_are_unique():
    ids = [case["id"] for case in CASES]

    assert len(ids) == len(set(ids))


def test_given_the_validation_source_when_its_rule_ids_are_listed_then_every_one_has_a_refusing_case():
    source = (PACKAGE / "schedule_policy" / "policy.py").read_text("utf-8")
    rules = set(re.findall(r'(?:Problem\(|\()\s*"([a-z]+(?:_[a-z]+)+)"', source))
    covered = {rule for case in CASES for rule in case["rules"]}

    assert rules
    assert rules <= covered


def test_given_the_boundaries_when_listed_then_valid_and_invalid_rows_exist_on_both_sides():
    valid = {case["id"] for case in CASES if not case["rules"]}

    assert {"window_exactly_60_minutes", "window_exactly_12_hours", "overview_at_quiet_end_is_outside"} <= valid
    assert {"window_59_minutes", "window_721_minutes", "overview_at_quiet_start_is_inside"} <= {
        case["id"] for case in CASES if case["rules"]
    }
