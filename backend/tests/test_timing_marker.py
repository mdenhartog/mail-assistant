"""U-web-settings-62 (CR-05): the wall-clock decoy comparison runs in the nightly workflow, not in the suite."""

import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
NIGHTLY_WORKFLOW = BACKEND.parent / ".github" / "workflows" / "nightly.yml"


def _pytest_options() -> dict[str, object]:
    with (BACKEND / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["tool"]["pytest"]["ini_options"]


def test_given_the_pytest_options_when_read_then_the_timing_marker_is_registered_and_off_by_default() -> None:
    options = _pytest_options()

    assert any(str(marker).startswith("timing:") for marker in options["markers"])  # type: ignore[index]
    assert '-m "not timing"' in str(options["addopts"])


def test_given_the_nightly_workflow_when_read_then_it_runs_the_timing_tests() -> None:
    workflow = NIGHTLY_WORKFLOW.read_text(encoding="utf-8")

    assert "pytest -m timing" in workflow
    assert "--no-cov" in workflow
