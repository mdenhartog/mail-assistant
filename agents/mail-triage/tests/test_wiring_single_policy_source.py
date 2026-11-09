"""The interim policy source exists once: a second class of the same name would silently shadow the first."""

from __future__ import annotations

import ast
from pathlib import Path

WIRING = Path(__file__).resolve().parents[1] / "app" / "wiring.py"


def test_given_the_wiring_module_when_parsed_then_default_policy_source_is_defined_once() -> None:
    tree = ast.parse(WIRING.read_text(encoding="utf-8"))
    definitions = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "DefaultPolicySource"]

    assert len(definitions) == 1
