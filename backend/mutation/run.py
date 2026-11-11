"""Local mutation run of one pure module with cosmic-ray (plan: test rules and levels, U-web-settings-10).

Run from `backend/`, one module at a time, without docker:

    uv run --with cosmic-ray python mutation/run.py app/auth/code_hash.py

The session file and the generated config live outside the repository (default: the system temp directory).
Type annotations are excluded: CPython 3.14 evaluates them lazily, so a mutant in an annotation is equivalent.
After `cosmic-ray init` the runner marks every mutant whose span lies inside an annotation as skipped, found with
the `ast` module (parameters, return values and annotated assignments). Skipped mutants are not in the score.
"""

import argparse
import ast
import importlib
import shutil
import subprocess  # the runner only starts cosmic-ray with fixed argument lists
import sys
import tempfile
from pathlib import Path
from typing import Any

Position = tuple[int, int]
Range = tuple[Position, Position]

DEFAULT_TESTS = ("tests/auth", "tests/test_pure_modules.py")
TEST_TIMEOUT_SECONDS = 30
PASS_THRESHOLD_PERCENT = 85.0


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


def main(argv: list[str] | None = None) -> int:
    """Initialise, filter, execute and rate one module."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("module", help="module path relative to backend/, e.g. app/auth/code_hash.py")
    parser.add_argument("--tests", nargs="+", default=list(DEFAULT_TESTS), help="test paths that must kill the mutants")
    parser.add_argument("--session-dir", type=Path, default=Path(tempfile.gettempdir()) / "mail-assistant-mutation")
    args = parser.parse_args(argv)

    module = Path(args.module)
    args.session_dir.mkdir(parents=True, exist_ok=True)
    config = args.session_dir / f"{module.stem}.toml"
    session = args.session_dir / f"{module.stem}.sqlite"
    session.unlink(missing_ok=True)
    write_config(config, module.as_posix(), tuple(args.tests))
    _run(_tool("cosmic-ray"), "init", str(config), str(session))
    sys.stdout.write(f"skipped annotation mutants: {_skip_annotation_mutants(session)}\n")
    _run(_tool("cosmic-ray"), "exec", str(config), str(session))
    _run(_tool("cr-rate"), str(session), "--fail-over", str(100 - PASS_THRESHOLD_PERCENT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
