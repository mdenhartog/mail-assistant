"""The local mutation runner skips mutants inside type annotations (they are equivalent on CPython 3.14)."""

import importlib.util
import tomllib
from pathlib import Path
from types import ModuleType

RUN = Path(__file__).resolve().parents[1] / "mutation" / "run.py"

SOURCE = """\
LIMIT: int | None = 3


def f(a: int | str, *, b: bytes = b"") -> bytes | None:
    c: list[int] = [1 | 2]
    return b + c
"""


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutation_run", RUN)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_annotation_positions_are_skipped_and_code_positions_are_not() -> None:
    run = _load()
    ranges = run.annotation_ranges(SOURCE)
    # `int | None` of the constant (line 1, columns 7 to 17) and the BitOr inside it.
    assert run.in_annotation(ranges, (1, 11), (1, 12))
    # `int | str` of the parameter and `bytes | None` of the return value.
    assert run.in_annotation(ranges, (4, 9), (4, 18))
    assert run.in_annotation(ranges, (4, 42), (4, 54))
    # the local annotation `list[int]`
    assert run.in_annotation(ranges, (5, 7), (5, 16))
    # code: the default `b""`, the value `1 | 2`, and the constant value `3`
    assert not run.in_annotation(ranges, (4, 34), (4, 37))
    assert not run.in_annotation(ranges, (5, 20), (5, 25))
    assert not run.in_annotation(ranges, (1, 20), (1, 21))
    # a mutant that spans the whole assignment is code, not annotation
    assert not run.in_annotation(ranges, (1, 0), (1, 21))


def test_generated_config_is_valid_toml_for_the_module_and_tests(tmp_path: Path) -> None:
    run = _load()
    config = tmp_path / "c.toml"
    run.write_config(config, "app/auth/mask.py", ("tests/auth",))
    data = tomllib.loads(config.read_text(encoding="utf-8"))["cosmic-ray"]
    assert data["module-path"] == "app/auth/mask.py"
    assert "tests/auth" in data["test-command"]
    assert "--no-cov" in data["test-command"]
    assert data["distributor"]["name"] == "local"
