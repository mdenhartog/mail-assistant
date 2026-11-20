"""A source change in this package must make uv rebuild and reinstall it.

The backend and the agent install this package from a path with a fixed version.
Without cache keys uv only looks at pyproject.toml, so a long-lived environment
(the integration worktree) kept a copy from before RULES existed.
"""

import tomllib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def test_the_module_sources_are_a_uv_cache_key() -> None:
    config = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    keys = config["tool"]["uv"]["cache-keys"]

    assert {"file": "pyproject.toml"} in keys
    assert {"file": "schedule_policy/**/*"} in keys
