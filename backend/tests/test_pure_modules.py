"""Pure modules keep to the standard library and carry the mutation marker (plan: test rules, U-web-settings-10)."""

import ast
import sys
import tomllib
from pathlib import Path

import pytest

MARKER = "# pure module (mutation-gated)"
APP = Path(__file__).resolve().parents[1] / "app"
GATE = Path(__file__).resolve().parents[1] / "cosmic-ray.toml"
FORBIDDEN = {"fastapi", "starlette", "sqlalchemy", "httpx", "httpcore", "aiosmtplib", "requests", "socket", "ssl"}
PURE_MODULES = [m.removeprefix("app/") for m in tomllib.loads(GATE.read_text(encoding="utf-8"))["mutation"]["modules"]]
PURE_DOTTED = {"app." + m.removesuffix(".py").replace("/", ".") for m in PURE_MODULES}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(("." if node.level else "") + (node.module or ""))
    return names


def _has_marker(path: Path) -> bool:
    return MARKER in path.read_text(encoding="utf-8").splitlines()[:3]


@pytest.mark.parametrize("relative", PURE_MODULES)
def test_listed_pure_module_has_the_marker_and_imports_only_the_standard_library(relative: str) -> None:
    path = APP / relative
    assert _has_marker(path)
    for name in _imports(path):
        top = name.split(".")[0]
        assert top not in FORBIDDEN
        # a pure module may use another pure module, nothing else of the application
        assert top in sys.stdlib_module_names or name in PURE_DOTTED, f"{relative} imports {name}"


def test_every_marked_module_is_listed() -> None:
    marked = {p.relative_to(APP).as_posix() for p in APP.rglob("*.py") if _has_marker(p)}
    assert marked >= set(PURE_MODULES)
