"""U-web-settings-70: case-insensitive env guards in both charts, and a disruption budget that allows one eviction.

Findings RT3-06 and SEC3-08 (guards) and RT3-08 (budget). pydantic-settings lowercases variable names and the last
duplicate wins, and Kubernetes does not order env entries for the reader, so `app_public_origin` next to the chart's
`APP_PUBLIC_ORIGIN` can win. Both charts therefore compare keys without regard to case, in the schema and the template.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
APP_CHART = ROOT / "deploy" / "charts" / "app"
WORKER_CHART = ROOT / "deploy" / "charts" / "worker"
APP_LOCAL = ROOT / "deploy" / "envs" / "local" / "values.yaml"
WORKER_LOCAL = ROOT / "deploy" / "envs" / "local" / "mail-triage.yaml"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
DIGEST = "sha256:" + "d" * 64  # well formed, not an image anybody runs


def helm(chart: Path, release: str, values: Path, *sets: str) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    base = [HELM, "template", release, str(chart), "-f", str(values)]
    for item in sets:
        base += ["--set-json" if item.startswith("json:") else "--set", item.removeprefix("json:")]
    return subprocess.run(base, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def app(*sets: str) -> subprocess.CompletedProcess[str]:
    return helm(APP_CHART, "app", APP_LOCAL, *sets)


def worker(*sets: str) -> subprocess.CompletedProcess[str]:
    return helm(WORKER_CHART, "mail-triage", WORKER_LOCAL, *sets)


def set_env(path: str, key: str, value: str = "x") -> str:
    return f"json:{path}={json.dumps({key: value})}"


def production() -> list[str]:
    return [
        "environment=production",
        f"api.image.digest={DIGEST}",
        f"web.image.digest={DIGEST}",
        "json:certAlert.enabled=true",
    ]


def variants(name: str) -> list[str]:
    """The key as the chart writes it, in lower case, and in a mixed case."""
    mixed = "".join(c.lower() if i % 2 else c.upper() for i, c in enumerate(name))
    return sorted({name, name.lower(), mixed})


def docs(stdout: str, kind: str) -> list[dict[str, Any]]:
    return [d for d in yaml.safe_load_all(stdout) if d and d["kind"] == kind]


def env_names(stdout: str, kinds: tuple[str, ...], only: str | None = None) -> set[str]:
    names: set[str] = set()
    for kind in kinds:
        for doc in docs(stdout, kind):
            if only and doc["metadata"]["name"] != only:
                continue
            for container in doc["spec"]["template"]["spec"]["containers"]:
                names |= {e["name"] for e in container.get("env", [])}
    return names


# --- criterion 1: the app chart ------------------------------------------------------------------------------------

# Every name the chart sets in the api, plain and secret. The render test below compares this list with the template,
# so a key added to the template without a refusal fails there.
APP_CHART_SET = [
    "APP_USERNAME",
    "APP_EMAIL_ADDRESS",
    "APP_SMTP_HOST",
    "APP_SMTP_PORT",
    "APP_SMTP_FROM",
    "APP_PUBLIC_ORIGIN",
    "APP_NOTICE_INTERVAL_MINUTES",
    "APP_TRUSTED_PROXY_CIDRS",
    "APP_TRUSTED_PROXY_HOPS",
    "APP_ENVIRONMENT",
    "APP_DATABASE_URL",
    "APP_CODE_HASH_KEY",
    "APP_CSRF_KEY",
    "APP_USERNAME_HASH_KEY",
    "APP_SMTP_USER",
    "APP_SMTP_PASSWORD",
]


@needs_helm
@pytest.mark.parametrize("component", ["api", "web"])
@pytest.mark.parametrize("name", APP_CHART_SET)
@pytest.mark.parametrize("environment", ["production", "local"])
def test_given_an_env_key_the_app_chart_sets_in_any_case_when_templated_then_it_fails_naming_the_key(
    component: str, name: str, environment: str
) -> None:
    sets = production() if environment == "production" else [f"environment={environment}"]
    for key in variants(name):
        result = app(*sets, set_env(f"{component}.env", key))

        assert result.returncode != 0, f"{component}.env.{key} rendered"
        assert key in result.stderr, result.stderr


@needs_helm
def test_given_every_name_the_api_deployment_sets_when_compared_then_the_list_above_is_complete() -> None:
    names = env_names(app().stdout, ("Deployment",), only="app-api")

    assert names == set(APP_CHART_SET)


def test_given_the_app_schema_when_read_then_it_refuses_the_chart_set_keys_in_any_case() -> None:
    schema = json.loads((APP_CHART / "values.schema.json").read_text(encoding="utf-8"))
    pattern = schema["definitions"]["component"]["properties"]["env"]["propertyNames"]["not"]["pattern"]

    for name in ("USERNAME", "PUBLIC_ORIGIN", "CODE_HASH_KEY", "SMTP_PASSWORD", "EMAIL_ADDRESS"):
        assert f"[{name[0]}{name[0].lower()}]" in pattern, f"the schema pattern lacks APP_{name}"


# --- criterion 1: the worker chart ---------------------------------------------------------------------------------

WORKER_CHART_SET = [
    "ENVIRONMENT",
    "DATABASE_SSL",
    "DATABASE_CA_FILE",
    "DATABASE_OWNER_URL",
    "DATABASE_URL",
    "RUNTIME_ROLE_PASSWORD",
    "WEB_ROLE_PASSWORD",
]


@needs_helm
@pytest.mark.parametrize("name", WORKER_CHART_SET)
def test_given_a_worker_env_key_the_chart_owns_in_any_case_when_templated_then_it_fails_naming_the_key(
    name: str,
) -> None:
    for key in variants(name):
        result = worker(set_env("env", key))

        assert result.returncode != 0, f"env.{key} rendered"
        assert key in result.stderr, result.stderr


@needs_helm
def test_given_a_worker_env_key_the_chart_does_not_own_when_templated_then_it_renders() -> None:
    result = worker(set_env("env", "POLL_INTERVAL_SECONDS", "30"))

    assert result.returncode == 0, result.stderr


@needs_helm
def test_given_every_name_the_worker_and_the_job_set_when_compared_then_the_list_above_is_covered() -> None:
    names = env_names(worker().stdout, ("Deployment", "Job"))

    assert names - {"POLL_INTERVAL_SECONDS"} <= set(WORKER_CHART_SET), names


def test_given_the_worker_schema_when_read_then_it_refuses_the_chart_owned_env_keys_in_any_case() -> None:
    schema = json.loads((WORKER_CHART / "values.schema.json").read_text(encoding="utf-8"))
    pattern = schema["properties"]["env"]["propertyNames"]["not"]["pattern"]

    for name in ("ENVIRONMENT", "DATABASE_", "RUNTIME_ROLE_PASSWORD", "WEB_ROLE_PASSWORD"):
        assert f"[{name[0]}{name[0].lower()}]" in pattern, f"the schema pattern lacks {name}"


# --- criterion 3: the disruption budget ----------------------------------------------------------------------------


@needs_helm
@pytest.mark.parametrize("environment", ["production", "local"])
def test_given_production_or_local_values_when_rendered_then_the_api_budget_allows_one_disruption(
    environment: str,
) -> None:
    sets = production() if environment == "production" else [f"environment={environment}"]
    result = app(*sets)

    assert result.returncode == 0, result.stderr
    budgets = {d["metadata"]["name"]: d["spec"] for d in docs(result.stdout, "PodDisruptionBudget")}
    assert budgets["app-api"]["maxUnavailable"] == 1
    assert "minAvailable" not in budgets["app-api"]


def test_given_the_chart_defaults_and_the_local_values_when_read_then_the_budget_is_max_unavailable_one() -> None:
    for path in (APP_CHART / "values.yaml", APP_LOCAL):
        budget = yaml.safe_load(path.read_text(encoding="utf-8")).get("podDisruptionBudget")

        if path == APP_CHART / "values.yaml":
            assert budget == {"maxUnavailable": 1}, path
        else:
            assert budget is None, "the local values inherit the chart default"


@needs_helm
@pytest.mark.parametrize("minimum", [1, 2])
def test_given_min_available_not_below_the_api_replicas_when_templated_then_the_schema_refuses(minimum: int) -> None:
    budget = json.dumps({"minAvailable": minimum, "maxUnavailable": None})
    result = app(f"json:podDisruptionBudget={budget}")

    assert result.returncode != 0, "minAvailable >= api.replicas rendered"
    assert "podDisruptionBudget" in result.stderr or "minAvailable" in result.stderr


@needs_helm
def test_given_both_min_available_and_max_unavailable_when_templated_then_the_schema_refuses() -> None:
    result = app('json:podDisruptionBudget={"minAvailable":0,"maxUnavailable":1}')

    assert result.returncode != 0


@needs_helm
def test_given_min_available_below_the_api_replicas_when_templated_then_it_renders_that_value() -> None:
    result = app('json:podDisruptionBudget={"minAvailable":0,"maxUnavailable":null}')

    assert result.returncode == 0, result.stderr
    api = next(d for d in docs(result.stdout, "PodDisruptionBudget") if d["metadata"]["name"] == "app-api")
    assert api["spec"]["minAvailable"] == 0
