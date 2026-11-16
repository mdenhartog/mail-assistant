"""The agent refuses the same category names as the shared contract file (RED-004)."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from app.adapters.gmail_resort import LABEL_PREFIX, is_category_label

_FILE = Path(__file__).resolve().parents[4] / "packages" / "category-policy" / "contract" / "category_cases.json"
_CASES: list[dict[str, Any]] = json.loads(_FILE.read_text("utf-8"))["category"]
_RESERVED = {"other", "archive"}


def _label(name: str) -> str:
    return f"{LABEL_PREFIX}{unicodedata.normalize('NFKC', name.strip()).strip()}"


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_given_a_contract_case_when_made_a_label_then_the_adapter_agrees_with_the_policy(case: dict[str, Any]) -> None:
    label = _label(case["name"])
    name_rules = [
        r for r in case["rules"] if r.startswith("name_") and r not in ("name_duplicate", "name_label_exists")
    ]
    if not name_rules and label.removeprefix(LABEL_PREFIX).casefold() not in _RESERVED:
        assert is_category_label(label)
    elif ".." in label or "name_slash" in name_rules or "name_reserved" in name_rules:
        assert not is_category_label(label)
