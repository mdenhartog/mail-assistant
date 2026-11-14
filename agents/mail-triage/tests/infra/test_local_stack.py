"""U-web-settings-73: the local week-test stack (compose profile ``local``, scripts/local-stack.mjs, CI).

Static checks only: the compose files and the workflow are parsed as YAML, and the script's functions are tested by
``scripts/local-stack.test.mjs`` (a temp directory and a fake runner). Nothing here starts docker.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
COMPOSE = ROOT / "compose.yaml"
STACK_ENV = ROOT / "deploy" / "local" / "stack.env"
CI = ROOT / ".github" / "workflows" / "ci.yml"
NODE = shutil.which("node")
LOCAL_SERVICES = {"db", "mail", "mail-triage-migrate", "mail-triage", "api", "web", "edge"}
SPEC_DEFAULTS = {
    "APP_RATE_LIMIT_PER_MINUTE": ("API_RATE_LIMIT_PER_MINUTE", "30"),
    "APP_RESEND_COOLDOWN_SECONDS": ("API_RESEND_COOLDOWN_SECONDS", "60"),
    "APP_CODES_PER_HOUR": ("API_CODES_PER_HOUR", "5"),
    "APP_MAX_ATTEMPTS": ("API_MAX_ATTEMPTS", "5"),
    "APP_OPEN_LOGIN_REQUESTS_PER_CLIENT": ("API_OPEN_LOGIN_REQUESTS_PER_CLIENT", "10"),
    "APP_LOGIN_REQUESTS_PER_CLIENT_PER_HOUR": ("API_LOGIN_REQUESTS_PER_CLIENT_PER_HOUR", "20"),
}
RAISED_BY_CI = {
    "API_RATE_LIMIT_PER_MINUTE": "1000",
    "API_RESEND_COOLDOWN_SECONDS": "1",
    "API_CODES_PER_HOUR": "1000",
    "API_OPEN_LOGIN_REQUESTS_PER_CLIENT": "1000",
    "API_LOGIN_REQUESTS_PER_CLIENT_PER_HOUR": "1000",
}


def all_services() -> dict[str, Any]:
    root = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services: dict[str, Any] = dict(root["services"])
    for include in root["include"]:
        services.update(yaml.safe_load((ROOT / include).read_text(encoding="utf-8"))["services"])
    return services


def local_services() -> dict[str, Any]:
    return {
        name: service
        for name, service in all_services().items()
        if not service.get("profiles") or "local" in service["profiles"]
    }


def env_file(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)
    return {key.strip(): value.strip() for key, value in pairs if not key.startswith("#")}


def resolve(value: str, variables: dict[str, str]) -> str:
    """``${NAME:-default}`` as compose reads it: the variable when set, else the default."""
    match = re.fullmatch(r"\$\{([A-Z_]+):-([^}]*)\}", str(value))
    assert match, f"{value!r} is not a reference with a default"
    return variables.get(match.group(1), match.group(2))


def ci_job(name: str) -> dict[str, Any]:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"][name]


# -- criterion 1 ---------------------------------------------------------------------------------------------------


def test_given_the_compose_files_when_parsed_then_the_local_profile_is_exactly_the_seven_services() -> None:
    assert set(local_services()) == LOCAL_SERVICES
    for name in ("mail", "mail-triage-migrate", "mail-triage", "api", "web", "edge"):
        assert "local" in all_services()[name]["profiles"], name


def test_given_the_local_services_when_parsed_then_every_published_port_is_on_the_loopback() -> None:
    ports = [port for service in local_services().values() for port in service.get("ports", [])]

    assert ports
    assert all(str(port).startswith("127.0.0.1:") for port in ports)


def test_given_the_local_services_when_parsed_then_the_services_are_shared_with_prod_like_not_copied() -> None:
    services = all_services()

    for name in ("mail", "api", "web", "edge"):
        assert set(services[name]["profiles"]) == {"prod-like", "local"}, name
    assert not [name for name in services if name.endswith("-local") or name.startswith("local-")]


def test_given_the_local_profile_when_parsed_then_it_sets_none_of_the_e2e_limit_overrides() -> None:
    stack = env_file(STACK_ENV)

    assert not [name for name in stack if name in {v[0] for v in SPEC_DEFAULTS.values()}]
    for service in local_services().values():
        for name, value in service.get("environment", {}).items():
            if name in SPEC_DEFAULTS:
                assert resolve(value, stack) == SPEC_DEFAULTS[name][1], name  # with the local settings: the spec value


# -- criterion 2 ---------------------------------------------------------------------------------------------------


def test_given_the_api_service_when_parsed_then_every_limit_is_a_variable_with_the_spec_default() -> None:
    environment = all_services()["api"]["environment"]

    for name, (variable, default) in SPEC_DEFAULTS.items():
        assert environment[name] == f"${{{variable}:-{default}}}", name


@pytest.mark.parametrize("job", ["prod-like", "gxp"])
def test_given_the_ci_jobs_that_bring_up_the_stack_when_parsed_then_they_set_the_raised_limits(job: str) -> None:
    env = {key: str(value) for key, value in ci_job(job)["env"].items()}

    for variable, value in RAISED_BY_CI.items():
        assert env[variable] == value, variable


def test_given_the_raised_limits_when_searched_then_only_the_ci_jobs_and_no_compose_default_hold_them() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert not re.search(r'APP_(RATE_LIMIT_PER_MINUTE|CODES_PER_HOUR|OPEN_LOGIN\w*|LOGIN_REQUESTS\w*):\s*"1000"', text)
    assert not re.search(r'APP_RESEND_COOLDOWN_SECONDS:\s*"1"', text)


# -- criterion 4 ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["mail-triage", "mail-triage-migrate"])
def test_given_the_agent_services_when_parsed_then_local_is_production_verify_full_and_dev_keeps_the_weak_defaults(
    name: str,
) -> None:
    service = all_services()[name]
    environment = service["environment"]
    stack = env_file(STACK_ENV)

    assert "local" in service["profiles"]
    assert resolve(environment["ENVIRONMENT"], stack) == "production"
    assert resolve(environment["DATABASE_SSL"], stack) == "verify-full"
    assert resolve(environment["ENVIRONMENT"], {}) == "development"  # the dev profile: no stack file
    assert resolve(environment["DATABASE_SSL"], {}) == "disable"
    assert environment["DATABASE_CA_FILE"] == "/certs/ca.crt"
    assert "../../deploy/prod-like/certs:/certs:ro" in service["volumes"]


def test_given_the_stack_file_when_read_then_it_holds_settings_and_no_secret() -> None:
    stack = env_file(STACK_ENV)

    assert stack == {"LOCAL_AGENT_ENVIRONMENT": "production", "LOCAL_AGENT_DATABASE_SSL": "verify-full"}


def test_given_the_script_when_read_then_it_passes_the_stack_file_after_the_env_file() -> None:
    text = (ROOT / "scripts" / "local-stack.mjs").read_text(encoding="utf-8")

    line = re.search(r"const ENV_FILES = \[(.*)\];", text)

    assert line is not None
    assert re.findall(r'"([^"]+)"', line.group(1)) == [".env", "deploy/local/stack.env", "deploy/local/secrets.env"]


# -- criteria 3 and 5: the script, through its node tests -----------------------------------------------------------


@pytest.fixture(scope="module")
def node_results() -> dict[str, bool]:
    if NODE is None:
        pytest.skip("node is needed to run the tests of the script")
    result = subprocess.run(  # noqa: S603
        [NODE, "--test", "--test-reporter=tap", "scripts/local-stack.test.mjs"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=300,
        check=False,
    )
    found = {
        match.group(2): match.group(1) is None
        for match in re.finditer(r"^\s*(not )?ok \d+ - (.+?)(?: # .*)?$", result.stdout, re.MULTILINE)
    }
    assert found, result.stdout + result.stderr
    return found


@pytest.mark.parametrize("criterion", ["criterion 3:", "criterion 5:"])
def test_given_the_script_when_its_node_tests_run_then_every_test_of_the_criterion_passes(
    node_results: dict[str, bool], criterion: str
) -> None:
    mine = {name: ok for name, ok in node_results.items() if name.startswith(criterion)}

    assert len(mine) >= 3
    assert all(mine.values()), [name for name, ok in mine.items() if not ok]


@pytest.mark.parametrize(
    "criterion", ["U-75 criterion 1:", "U-75 criterion 2:", "U-75 criterion 3:", "U-75 criterion 4:"]
)
def test_given_the_runtime_password_unit_when_its_node_tests_run_then_every_criterion_has_a_passing_test(
    node_results: dict[str, bool], criterion: str
) -> None:
    mine = {name: ok for name, ok in node_results.items() if name.startswith(criterion)}

    assert mine, criterion
    assert all(mine.values()), [name for name, ok in mine.items() if not ok]


def test_given_the_warning_tests_when_its_node_tests_run_then_the_database_url_warning_is_covered(
    node_results: dict[str, bool],
) -> None:
    mine = {name: ok for name, ok in node_results.items() if name.startswith("U-75 warning:")}

    assert len(mine) >= 3
    assert all(mine.values()), [name for name, ok in mine.items() if not ok]


def test_given_the_script_when_its_node_tests_run_then_all_of_them_pass(node_results: dict[str, bool]) -> None:
    assert all(node_results.values()), [name for name, ok in node_results.items() if not ok]


# -- criterion 6: the CI job -----------------------------------------------------------------------------------------


def test_given_the_prod_like_job_when_parsed_then_it_still_runs_the_journey_with_the_limits_from_its_env() -> None:
    job = ci_job("prod-like")
    commands = "\n".join(str(step.get("run", "")) for step in job["steps"])

    assert "pnpm --filter web e2e" in commands
    assert "docker compose --profile prod-like up -d --build --wait" in commands
    assert "mail-triage-migrate" in commands
    assert {key: str(job["env"][key]) for key in RAISED_BY_CI} == RAISED_BY_CI
