"""The mutation gate covers every pure security module and cannot go stale (plan: U-web-settings-44)."""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
MARKER = "# pure module (mutation-gated)"
WORKFLOW = BACKEND.parent / ".github" / "workflows" / "mutation.yml"
MARGIN_POINTS = 5.0


def _runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutation_run", BACKEND / "mutation" / "run.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _marked() -> set[str]:
    return {
        p.relative_to(BACKEND).as_posix()
        for p in APP.rglob("*.py")
        if MARKER in p.read_text(encoding="utf-8").splitlines()[:3]
    }


def test_gate_lists_exactly_the_marked_modules() -> None:
    gate = _runner().load_gate()
    assert set(gate.modules) == _marked()
    assert len(gate.modules) == len(set(gate.modules))


def test_a_marked_module_missing_from_the_gate_is_reported(tmp_path: Path) -> None:
    runner = _runner()
    config = tmp_path / "cosmic-ray.toml"
    listed = sorted(_marked())[1:]
    modules = ", ".join(f'"{m}"' for m in listed)
    config.write_text(
        f'[mutation]\nmodules = [{modules}]\ntests = ["tests"]\n'
        "max-survived-percent = 15\ntarget-survived-percent = 10\nskip-annotations = true\n",
        encoding="utf-8",
    )
    gate = runner.load_gate(config)
    assert runner.missing_from_gate(gate, _marked()) == {sorted(_marked())[0]}


def test_every_listed_module_exists() -> None:
    for module in _runner().load_gate().modules:
        assert (BACKEND / module).is_file(), module


def test_annotations_are_excluded_from_the_score() -> None:
    assert _runner().load_gate().skip_annotations is True


def test_target_keeps_a_margin_under_the_ci_threshold() -> None:
    gate = _runner().load_gate()
    assert gate.max_survived_percent == 15.0
    assert gate.target_survived_percent <= gate.max_survived_percent - MARGIN_POINTS


def test_workflow_runs_one_job_per_module_from_the_config() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"^\s+schedule:", text, re.MULTILINE)
    assert re.search(r"^\s+workflow_dispatch:", text, re.MULTILINE)
    before_backend, backend = text.split("\n  backend:\n", 1)
    matrix_job = before_backend.split("\n  backend-matrix:\n", 1)[1]
    # the module list comes from backend/cosmic-ray.toml, never from a second list in the workflow
    assert "cosmic-ray.toml" in matrix_job
    assert "needs: backend-matrix" in backend
    assert "fromJSON(needs.backend-matrix.outputs.modules)" in backend
    assert "fail-fast: false" in backend
    assert "working-directory: backend" in backend
    assert "mutation/run.py" in backend
    assert "app/" not in backend


@pytest.mark.parametrize(
    ("output", "expected"),
    [("53.125\n", 53.125), ("0.00\n", 0.0), ("\n12.5", 12.5)],
)
def test_survival_percent_reads_the_cr_rate_output(output: str, expected: float) -> None:
    assert _runner().survival_percent(output) == expected


def test_survival_percent_rejects_unreadable_output() -> None:
    with pytest.raises(ValueError, match="cr-rate"):
        _runner().survival_percent("no number here")


def test_verdict_fails_above_the_gate_and_flags_above_the_target() -> None:
    runner = _runner()
    gate = runner.load_gate()
    assert runner.verdict(gate, 0.0) == "pass"
    assert runner.verdict(gate, gate.target_survived_percent) == "pass"
    assert runner.verdict(gate, gate.target_survived_percent + 0.1) == "above-target"
    assert runner.verdict(gate, gate.max_survived_percent) == "above-target"
    assert runner.verdict(gate, gate.max_survived_percent + 0.1) == "fail"
