"""U-web-settings-02: the backend depends on the shared schedule-policy package and its image carries it (ADR-0028)."""

import importlib
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DOCKERFILE = BACKEND / "Dockerfile"
COMPOSE = ROOT / "compose.yaml"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def runtime_env() -> dict[str, str]:
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    stage = lines[max(i for i, line in enumerate(lines) if line.startswith("FROM ")) :]
    env: dict[str, str] = {}
    for line in stage:
        if line.startswith("ENV "):
            for name, value in re.findall(r'(\w+)=("[^"]*"|\S*)', line[4:]):
                env[name] = value.strip('"')
    return env


def compose_service(name: str) -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"][name]


def test_given_the_backend_environment_when_imported_then_schedule_policy_is_available() -> None:
    policy = importlib.import_module("schedule_policy.policy")  # the package ships no type stubs

    assert policy.DEFAULT_POLICY is not None


def test_given_the_backend_project_when_read_then_schedule_policy_is_a_locked_path_dependency() -> None:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    lock = (BACKEND / "uv.lock").read_text(encoding="utf-8")

    assert "schedule-policy" in project["project"]["dependencies"]
    assert project["tool"]["uv"]["sources"]["schedule-policy"] == {"path": "../packages/schedule-policy"}
    assert (BACKEND / "../packages/schedule-policy/pyproject.toml").resolve().is_file()
    assert re.search(r'^name = "schedule-policy"$', lock, re.MULTILINE)
    assert 'directory = "../packages/schedule-policy"' in lock


def test_given_the_dockerfile_when_read_then_the_build_context_is_the_repo_root_and_carries_the_package() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")

    assert re.search(
        r"^COPY packages/schedule-policy/schedule_policy /srv/packages/schedule-policy/schedule_policy$", text, re.M
    )
    assert re.search(
        r"^COPY packages/schedule-policy/pyproject.toml /srv/packages/schedule-policy/pyproject.toml$", text, re.M
    )
    assert re.search(r"^COPY backend/pyproject.toml backend/uv.lock \./$", text, re.M)
    assert re.search(r"^COPY backend/app \./app$", text, re.M)
    assert re.search(r"^WORKDIR /srv/backend$", text, re.M)  # mirrors the repo so ../packages resolves


def test_given_the_runtime_image_when_zoneinfo_resolves_then_only_the_pinned_tzdata_wheel_can_win() -> None:
    env = runtime_env()

    assert "PYTHONTZPATH" in env, "set PYTHONTZPATH so that the pinned tzdata wheel is the only source (ADR-0028)"
    probe = (
        "import zoneinfo, pathlib, tzdata;"
        "assert all(not pathlib.Path(p).is_dir() for p in zoneinfo.TZPATH), zoneinfo.TZPATH;"
        "zoneinfo.ZoneInfo('Pacific/Kiritimati')"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONTZPATH": env["PYTHONTZPATH"]},
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert env["PYTHONTZPATH"] != ""
    assert not Path(env["PYTHONTZPATH"]).exists()
    assert "/srv/backend/.venv/bin" in env["PATH"]


def test_given_the_runtime_image_when_read_then_tzdata_is_locked() -> None:
    assert re.search(r'^name = "tzdata"$', (BACKEND / "uv.lock").read_text(encoding="utf-8"), re.MULTILINE)


def test_given_the_dockerignore_when_read_then_only_the_allow_listed_paths_enter_the_context() -> None:
    lines = (BACKEND / "Dockerfile.dockerignore").read_text(encoding="utf-8").splitlines()
    rules = [line for line in lines if line and not line.startswith("#")]

    assert rules[0] == "*"
    allowed = {line for line in rules if line.startswith("!")}
    assert allowed == {
        "!backend/pyproject.toml",
        "!backend/uv.lock",
        "!backend/app",
        "!packages/schedule-policy/pyproject.toml",
        "!packages/schedule-policy/schedule_policy",
    }
    text = "\n".join(lines)
    assert ".env" not in text.replace("*", "")  # nothing re-includes it; the deny-all already keeps it out
    assert "!.git" not in text
    assert "node_modules" not in "".join(allowed)


@pytest.mark.parametrize("name", ["api", "api-dev", "api-test"])
def test_given_the_compose_services_when_read_then_the_backend_builds_from_the_repo_root(name: str) -> None:
    build = compose_service(name)["build"]

    assert build["context"] == "."
    assert build["dockerfile"] == "backend/Dockerfile"


@pytest.mark.parametrize("name", ["api-dev", "api-test"])
def test_given_the_dev_and_test_services_when_read_then_they_work_in_the_mirrored_backend_directory(name: str) -> None:
    service = compose_service(name)

    assert service["build"]["target"] == "build"
    assert service["working_dir"] == "/srv/backend"
    assert all(volume.split(":")[1] != "/srv" for volume in service["volumes"])


def test_given_the_ci_images_job_when_read_then_the_api_image_is_linted_and_built_from_the_repo_root() -> None:
    steps = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["images"]["steps"]
    build = next(step for step in steps if step.get("name") == "build api")["with"]
    lint = next(step for step in steps if step.get("name") == "hadolint")["run"]

    assert build["context"] == "."
    assert build["file"] == "backend/Dockerfile"
    assert "hadolint/hadolint:v2.15.1 < backend/Dockerfile" in lint
