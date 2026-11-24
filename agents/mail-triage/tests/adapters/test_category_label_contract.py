"""The agent refuses the same category names as the shared contract file (RED-004, policy v3, ADR-0060).

A label is the canonical list name, with no prefix. The adapter renames a managed label only to a name the shared
policy accepts for a category, so every case of the contract file must give the same verdict here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.adapters.gmail_resort import GmailResort, LabelRefused
from app.core.managed import ManagedLabel, ManagedSet, Role
from category_policy import label_for
from tests.fakes.fake_gmail import FakeGmail

_FILE = Path(__file__).resolve().parents[4] / "packages" / "category-policy" / "contract" / "category_cases.json"
_CASES: list[dict[str, Any]] = json.loads(_FILE.read_text("utf-8"))["category"]
_LEN_PLACEHOLDER = re.compile(r"__label_len_(\d+)__")
_LIST_RULES = ("name_duplicate", "name_label_exists", "name_setting_clash")  # decided with the list, not by a label


def _name(raw: str) -> str:
    """Expand ``__label_len_N__`` into a valid nested name whose label has N characters (segments of 40 letters)."""
    match = _LEN_PLACEHOLDER.fullmatch(raw)
    if match is None:
        return raw
    length = int(match.group(1))
    segments: list[str] = []
    while length > 0:
        take = min(40, length)
        segments.append("a" * take)
        length -= take + 1
    return "/".join(segments)


def _accepts(label: str) -> bool:
    """Whether the adapter renames a managed topic label to ``label``."""
    gmail = FakeGmail()
    label_id = gmail.add_label("Start")
    resort = GmailResort(gmail, ManagedSet([ManagedLabel("Start", label_id, Role.TOPIC)]), sleep=lambda _s: None)
    resort.list_labels()
    try:
        resort.rename_label(label_id, label)
    except LabelRefused:
        return False
    return True


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_given_a_contract_case_when_made_a_label_then_the_agent_agrees_with_the_policy(case: dict[str, Any]) -> None:
    label = label_for(_name(case["name"]))
    name_rules = [r for r in case["rules"] if r.startswith("name_") and r not in _LIST_RULES]

    assert _accepts(label) is (not name_rules)
