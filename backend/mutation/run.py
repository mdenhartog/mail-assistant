"""Mutation gate of the pure security modules with cosmic-ray (ADR-0030 item 4; U-web-settings-10, -11, -44).

`cosmic-ray.toml` lists the modules, the tests that must kill the mutants and the thresholds. Run from `backend/`
without docker, one module or the whole gate (foreground; the exit code is 1 when a module is over the gate):

    uv run python mutation/run.py app/auth/code_hash.py
    uv run python mutation/run.py --all

The session file and the generated config live outside the repository (default: the system temp directory).
Type annotations are excluded: CPython 3.14 evaluates them lazily, so a mutant in an annotation is equivalent.
After `cosmic-ray init` the runner marks every mutant whose span lies inside an annotation as skipped, found with
the `ast` module (parameters, return values and annotated assignments). Skipped mutants are not in the score.
"""

import argparse
import ast
import importlib
import re
import shutil
import subprocess  # the runner only starts cosmic-ray with fixed argument lists
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Position = tuple[int, int]
Range = tuple[Position, Position]

GATE_CONFIG = Path(__file__).resolve().parents[1] / "cosmic-ray.toml"
TEST_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Gate:
    """The mutation gate read from cosmic-ray.toml."""

    modules: tuple[str, ...]
    tests: tuple[str, ...]
    max_survived_percent: float
    target_survived_percent: float
    skip_annotations: bool


def load_gate(path: Path = GATE_CONFIG) -> Gate:
    """Read the gate from the config file."""
    section = tomllib.loads(path.read_text(encoding="utf-8"))["mutation"]
    return Gate(
        modules=tuple(section["modules"]),
        tests=tuple(section["tests"]),
        max_survived_percent=float(section["max-survived-percent"]),
        target_survived_percent=float(section["target-survived-percent"]),
        skip_annotations=bool(section["skip-annotations"]),
    )


def missing_from_gate(gate: Gate, marked: set[str]) -> set[str]:
    """Return the marked modules the gate does not list."""
    return marked - set(gate.modules)


def survival_percent(output: str) -> float:
    """Read the percentage of surviving mutants from the cr-rate output."""
    found = re.search(r"\d+(?:\.\d+)?", output)
    if found is None:
        raise ValueError(f"cannot read a number from the cr-rate output: {output!r}")
    return float(found.group())


def verdict(gate: Gate, survived_percent: float) -> str:
    """Return pass, above-target or fail for a module score."""
    if survived_percent > gate.max_survived_percent:
        return "fail"
    if survived_percent > gate.target_survived_percent:
        return "above-target"
    return "pass"


def annotation_ranges(source: str) -> list[Range]:
    """Return the (line, column) spans of every type annotation in the source."""
    spans: list[Range] = []
    for node in ast.walk(ast.parse(source)):
        annotations: list[ast.expr | None] = []
        if isinstance(node, ast.arg | ast.AnnAssign):
            annotations.append(node.annotation)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            annotations.append(node.returns)
        spans.extend(
            ((a.lineno, a.col_offset), (a.end_lineno or a.lineno, a.end_col_offset or a.col_offset))
            for a in annotations
            if a is not None
        )
    return spans


def in_annotation(ranges: list[Range], start: Position, end: Position) -> bool:
    """True when the span start..end lies completely inside one of the annotation spans."""
    return any(low <= start and end <= high for low, high in ranges)


def _test_command(tests: tuple[str, ...]) -> str:
    args = ", ".join(f'\\"{t}\\"' for t in ("-x", "-q", "--no-cov", "-p", "no:cacheprovider", *tests))
    return (
        'uv run --no-sync python -c "import faulthandler, sys, pytest; '
        f'faulthandler.dump_traceback_later({TEST_TIMEOUT_SECONDS}, exit=True); sys.exit(pytest.main([{args}]))"'
    )


def write_config(path: Path, module: str, tests: tuple[str, ...]) -> None:
    """Write the cosmic-ray config for one module ; on Windows the test command ends itself after 30 s."""
    path.write_text(
        "[cosmic-ray]\n"
        f'module-path = "{module}"\n'
        "timeout = 90.0\n"
        "excluded-modules = []\n"
        f"test-command = '{_test_command(tests)}'\n\n"
        '[cosmic-ray.distributor]\nname = "local"\n',
        encoding="utf-8",
    )


def _skip_annotation_mutants(session: Path) -> int:
    work_db: Any = importlib.import_module("cosmic_ray.work_db")
    work_item: Any = importlib.import_module("cosmic_ray.work_item")
    skipped = 0
    cache: dict[str, list[Range]] = {}
    with work_db.use_db(str(session), work_db.WorkDB.Mode.open) as database:
        for item in list(database.pending_work_items):
            for mutation in item.mutations:
                path = str(mutation.module_path)
                if path not in cache:
                    cache[path] = annotation_ranges(Path(path).read_text(encoding="utf-8"))
                if in_annotation(cache[path], tuple(mutation.start_pos), tuple(mutation.end_pos)):
                    result = work_item.WorkResult(output="Annotation", worker_outcome=work_item.WorkerOutcome.SKIPPED)
                    database.set_result(item.job_id, result)
                    skipped += 1
                    break
    return skipped


def _tool(name: str) -> str:
    found = shutil.which(name, path=str(Path(sys.executable).parent))
    if found is None:
        sys.exit(f"{name} not found; start the runner with `uv run --with cosmic-ray python mutation/run.py ...`")
    return found


def _run(*command: str) -> None:
    subprocess.run(command, check=True)  # noqa: S603


def mutate(gate: Gate, module: str, session_dir: Path, tests: tuple[str, ...]) -> float:
    """Initialise, filter, execute and rate one module; return the percentage of surviving mutants."""
    path = Path(module)
    session_dir.mkdir(parents=True, exist_ok=True)
    config = session_dir / f"{path.stem}.toml"
    session = session_dir / f"{path.stem}.sqlite"
    session.unlink(missing_ok=True)
    write_config(config, path.as_posix(), tests)
    _run(_tool("cosmic-ray"), "init", str(config), str(session))
    if gate.skip_annotations:
        sys.stdout.write(f"skipped annotation mutants: {_skip_annotation_mutants(session)}\n")
    _run(_tool("cosmic-ray"), "exec", str(config), str(session))
    rated = subprocess.run(  # noqa: S603
        (_tool("cr-rate"), str(session)), check=True, capture_output=True, text=True
    )
    return survival_percent(rated.stdout)


def main(argv: list[str] | None = None) -> int:
    """Run one module or the whole gate; exit 1 when a module has more survivors than the gate allows."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("module", nargs="?", help="module path relative to backend/, e.g. app/auth/code_hash.py")
    parser.add_argument("--all", action="store_true", help="run every module of the gate (cosmic-ray.toml)")
    parser.add_argument("--tests", nargs="+", help="test paths that must kill the mutants (default: the gate's)")
    parser.add_argument("--session-dir", type=Path, default=Path(tempfile.gettempdir()) / "mail-assistant-mutation")
    args = parser.parse_args(argv)
    if args.all == (args.module is not None):
        parser.error("give either one module or --all")

    gate = load_gate()
    tests = tuple(args.tests) if args.tests else gate.tests
    modules = gate.modules if args.all else (Path(args.module).as_posix(),)
    scores: dict[str, float] = {}
    for module in modules:
        scores[module] = mutate(gate, module, args.session_dir, tests)
        sys.stdout.write(f"{module}: {scores[module]:.2f} % survived ({verdict(gate, scores[module])})\n")
    limits = f"gate {gate.max_survived_percent:g} %, target {gate.target_survived_percent:g} %"
    sys.stdout.write(f"\nsummary (survived mutants; {limits})\n")
    for module, score in scores.items():
        sys.stdout.write(f"  {score:6.2f} %  {verdict(gate, score):12}  {module}\n")
    return 1 if any(verdict(gate, score) == "fail" for score in scores.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
