"""Pure modules keep to the standard library and carry the mutation marker (plan: test rules, U-web-settings-10)."""

import ast
import sys
from pathlib import Path

import pytest

MARKER = "# pure module (mutation-gated)"
APP = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN = {"fastapi", "starlette", "sqlalchemy", "httpx", "httpcore", "aiosmtplib", "requests", "socket", "ssl"}
PURE_MODULES = [
    "auth/code_hash.py",
    "auth/mask.py",
    "auth/digest.py",
    "auth/return_to.py",
    "auth/event_rules.py",
    "auth/csrf.py",
    "limits.py",
    "clientaddr.py",
]


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(("." if node.level else "") + (node.module or "").split(".")[0])
    return names


def _has_marker(path: Path) -> bool:
    return MARKER in path.read_text(encoding="utf-8").splitlines()[:3]


@pytest.mark.parametrize("relative", PURE_MODULES)
def test_listed_pure_module_has_the_marker_and_imports_only_the_standard_library(relative: str) -> None:
    path = APP / relative
    assert _has_marker(path)
    for name in _imports(path):
        assert name in sys.stdlib_module_names, f"{relative} imports {name}"
        assert name not in FORBIDDEN


def test_every_marked_module_is_listed() -> None:
    marked = {p.relative_to(APP).as_posix() for p in APP.rglob("*.py") if _has_marker(p)}
    assert marked >= set(PURE_MODULES)
