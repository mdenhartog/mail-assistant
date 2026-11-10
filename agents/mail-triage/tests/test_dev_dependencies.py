"""U-quiet-hours-16c: the dev dependencies hold nothing the tests do not import (criterion 5)."""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_given_the_pyproject_when_the_dev_group_is_read_then_httpx2_is_not_in_it() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    names = {entry.split(">")[0].split("[")[0].strip() for entry in data["dependency-groups"]["dev"]}

    assert "httpx2" not in names
    assert "pytest" in names  # the parse found the group
