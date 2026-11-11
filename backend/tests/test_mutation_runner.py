"""The local mutation runner skips mutants inside type annotations (they are equivalent on CPython 3.14)."""

import importlib.util
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
    assert run.in_annotation(ranges, (4, 43), (4, 55))
    # the local annotation `list[int]`
    assert run.in_annotation(ranges, (5, 7), (5, 16))
    # code: the default `b""`, the value `1 | 2`, and the constant value `3`
    assert not run.in_annotation(ranges, (4, 35), (4, 38))
    assert not run.in_annotation(ranges, (5, 20), (5, 25))
    assert not run.in_annotation(ranges, (1, 20), (1, 21))
    # a mutant that spans the whole assignment is code, not annotation
    assert not run.in_annotation(ranges, (1, 0), (1, 21))
