"""The agent refuses the same category names as the shared contract file (RED-004, policy v2)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.adapters.gmail_resort import is_category_label
from category_policy import LABEL_PREFIX, label_for

_FILE = Path(__file__).resolve().parents[4] / "packages" / "category-policy" / "contract" / "category_cases.json"
_CASES: list[dict[str, Any]] = json.loads(_FILE.read_text("utf-8"))["category"]
_LEN_PLACEHOLDER = re.compile(r"__label_len_(\d+)__")
_LIST_RULES = ("name_duplicate", "name_label_exists")


def _name(raw: str) -> str:
    """Expand ``__label_len_N__`` into a valid nested name whose label has N characters."""
    match = _LEN_PLACEHOLDER.fullmatch(raw)
    if match is None:
        return raw
    size = int(match.group(1)) - len(LABEL_PREFIX)
    text = (f"{'a' * 39}/" * (size // 40 + 1))[:size]
    return text[:-1] + "a" if text.endswith("/") else text


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_given_a_contract_case_when_made_a_label_then_the_agent_agrees_with_the_policy(case: dict[str, Any]) -> None:
    label = label_for(_name(case["name"]))
    name_rules = [r for r in case["rules"] if r.startswith("name_") and r not in _LIST_RULES]

    assert is_category_label(label) is (not name_rules)
