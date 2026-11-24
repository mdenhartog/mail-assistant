"""U-label-prefix-removal-03, criterion 7: the old label prefix is in no agent core module (ADR-0060)."""

from __future__ import annotations

from pathlib import Path

import app.core
from app.usecases import overview

OLD_PREFIX = "Assistant" + "/"


def test_given_the_agent_core_when_searched_then_the_old_prefix_appears_nowhere() -> None:
    core = Path(app.core.__file__).parent
    hits = [path.name for path in core.glob("*.py") if OLD_PREFIX in path.read_text(encoding="utf-8")]
    assert hits == []


def test_given_the_overview_then_the_old_prefix_is_gone() -> None:
    assert OLD_PREFIX not in Path(overview.__file__).read_text(encoding="utf-8")
    assert not hasattr(overview, "LABEL_PREFIX")
