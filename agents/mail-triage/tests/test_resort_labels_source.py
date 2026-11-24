"""INT-010 U-18: the re-sort path holds no prefix, no fixed "Other" name and no name-based scope helper (AC 2, 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
MODULES = [
    "usecases/resort_build.py",
    "usecases/resort_apply.py",
    "usecases/move_back.py",
    "usecases/refile_report.py",
    "db/pg_resort.py",
]


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("word", ["OTHER_LABEL", "LABEL_PREFIX", "assistant_labels", "Assistant/"])
def test_the_module_holds_none_of_the_removed_names(module: str, word: str) -> None:
    assert word not in (APP / module).read_text(encoding="utf-8")
