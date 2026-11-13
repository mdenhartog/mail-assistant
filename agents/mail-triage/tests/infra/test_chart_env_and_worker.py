"""U-web-settings-66: the app chart owns the environment and the limits; the worker chart needs a digest in production.

Findings RT2-08 and SEC2-05 (ADR-0039). The settings of the api are read from `APP_*` variables, so a values file that
can set `APP_ENVIRONMENT` or a limit key can switch the production rules off or lift every limit. The chart must refuse
that, whatever the case of the key (pydantic-settings reads variables case-insensitively).
"""

from __future__ import annotations

import ast
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
CONFIG = ROOT / "backend" / "app" / "config.py"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
DIGEST = "sha256:" + "c" * 64  # well formed, not an image anybody runs

# Settings fields the chart sets itself (config.*, the secretKeyRef list) or that are harmless in `env`. A new field in
# Settings is in neither this set nor refused until somebody classifies it, and then the test below fails.
ENV_ALLOWED = {
    "app_name",
    "smtp_starttls",
    "smtp_timeout_seconds",
    # set by the chart from config.* (the chart value wins over env); listed so that a new field is a decision
    "username",
    "email_address",
    "smtp_host",
    "smtp_port",
    "smtp_from",
    "public_origin",
    "notice_interval_minutes",
    # secrets: they come from the Secret by reference, never from values
    "smtp_user",
    "smtp_password",
    "code_hash_key",
    "csrf_key",
    "username_hash_key",
}


def settings_fields() -> list[str]:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    settings = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Settings")
    return [n.target.id for n in settings.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]


def helm(
    chart: Path, release: str, values: Path, *sets: str, command: str = "template"
) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    base = [HELM, command, release, str(chart)] if command == "template" else [HELM, command, str(chart), "--strict"]
    base += ["-f", str(values)]
    for item in sets:
        base += ["--set-json" if item.startswith("json:") else "--set", item.removeprefix("json:")]
    return subprocess.run(base, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def app(*sets: str, command: str = "template") -> subprocess.CompletedProcess[str]:
    return helm(APP_CHART, "app", APP_LOCAL, *sets, command=command)


def worker(*sets: str, command: str = "template") -> subprocess.CompletedProcess[str]:
    return helm(WORKER_CHART, "mail-triage", WORKER_LOCAL, *sets, command=command)


def api_env(stdout: str) -> dict[str, str]:
    for doc in yaml.safe_load_all(stdout):
        if doc and doc["kind"] == "Deployment" and doc["metadata"]["name"] == "app-api":
            env = doc["spec"]["template"]["spec"]["containers"][0]["env"]
            return {e["name"]: e.get("value", "<secretKeyRef>") for e in env}
    raise AssertionError("no api Deployment rendered")


def production() -> list[str]:
    """What the schema requires of production, so that a refusal can only come from the key under test."""
    return [
        "environment=production",
        f"api.image.digest={DIGEST}",
        f"web.image.digest={DIGEST}",
        "json:certAlert.enabled=true",
    ]


def set_env(path: str, key: str, value: str) -> str:
    return f"json:{path}={json.dumps({key: value})}"


REFUSED = [
    ("APP_ENVIRONMENT", "development"),
    ("APP_ENVIRONMENT", "production"),
    ("app_environment", "development"),
    ("APP_CODES_PER_HOUR", "1000"),
    ("APP_MAX_ATTEMPTS", "1000"),
    ("APP_DATABASE_URL", "postgresql://x"),
    ("APP_DATABASE_SSL", "require"),
    ("APP_DATABASE_CA_FILE", "/x"),
    ("APP_TRUSTED_PROXY_CIDRS", "[]"),
    ("APP_TRUSTED_PROXY_HOPS", "5"),
    ("APP_RATE_LIMIT_PER_MINUTE", "100000"),
    ("APP_RATE_WINDOW_SECONDS", "1"),
    ("APP_OPEN_LOGIN_REQUEST_CAP", "100000"),
    ("APP_LIVE_REQUESTS_PER_USERNAME", "100000"),
    ("APP_LOGIN_REQUESTS_PER_CLIENT_PER_HOUR", "100000"),
    ("App_Codes_Per_Hour", "1000"),
]


@needs_helm
@pytest.mark.parametrize("component", ["api", "web"])
@pytest.mark.parametrize(("key", "value"), REFUSED)
@pytest.mark.parametrize("environment", ["production", "local"])
def test_given_an_env_key_the_chart_owns_when_templated_then_it_fails_naming_the_key(
    component: str, key: str, value: str, environment: str
) -> None:
    sets = production() if environment == "production" else [f"environment={environment}"]
    result = app(*sets, set_env(f"{component}.env", key, value))

    assert result.returncode != 0, f"{component}.env.{key} rendered"
    assert key in result.stderr, result.stderr


@needs_helm
@pytest.mark.parametrize("key", [f"APP_{f.upper()}" for f in settings_fields() if f not in ENV_ALLOWED])
def test_given_every_settings_field_that_is_not_allowed_when_set_in_api_env_then_the_chart_refuses(key: str) -> None:
    result = app(set_env("api.env", key, "1"))

    assert result.returncode != 0, f"api.env.{key} rendered; add it to the chart's refused keys or to ENV_ALLOWED"
    assert key in result.stderr


@needs_helm
def test_given_a_setting_that_the_chart_allows_when_set_in_api_env_then_it_renders() -> None:
    result = app(set_env("api.env", "APP_SMTP_TIMEOUT_SECONDS", "5"))

    assert result.returncode == 0, result.stderr
    assert api_env(result.stdout)["APP_SMTP_TIMEOUT_SECONDS"] == "5"


@needs_helm
@pytest.mark.parametrize(
    ("environment", "expected"), [("local", "development"), ("staging", "production"), ("production", "production")]
)
def test_given_an_environment_when_templated_then_app_environment_comes_from_it(
    environment: str, expected: str
) -> None:
    result = app(*(production() if environment == "production" else [f"environment={environment}"]))

    assert result.returncode == 0, result.stderr
    env = api_env(result.stdout)
    assert env["APP_ENVIRONMENT"] == expected
    assert [k for k in env if k.upper() == "APP_ENVIRONMENT"] == ["APP_ENVIRONMENT"]


def test_given_the_chart_defaults_when_read_then_api_env_does_not_set_the_environment() -> None:
    values = yaml.safe_load((APP_CHART / "values.yaml").read_text(encoding="utf-8"))

    assert not [k for k in values["api"].get("env", {}) if k.upper().startswith("APP_")]


@needs_helm
def test_given_the_local_values_when_linted_then_the_chart_passes_strict() -> None:
    result = app(command="lint")

    assert result.returncode == 0, result.stdout + result.stderr


def test_given_the_app_schema_when_read_then_it_forbids_the_chart_owned_keys_in_env() -> None:
    schema: dict[str, Any] = json.loads((APP_CHART / "values.schema.json").read_text(encoding="utf-8"))
    env = schema["definitions"]["component"]["properties"]["env"]

    assert "propertyNames" in env, "values.schema.json must forbid the chart-owned keys in api.env and web.env"


@needs_helm
def test_given_worker_values_with_production_and_no_digest_when_the_schema_runs_then_it_refuses() -> None:
    for command in ("template", "lint"):
        result = worker("environment=production", command=command)

        assert result.returncode != 0, command
        assert "digest" in result.stdout + result.stderr


@needs_helm
@pytest.mark.parametrize("digest", ["", "sha256:abc", "sha256:" + "G" * 64, "sha512:" + "a" * 64, "latest"])
def test_given_worker_values_with_production_and_a_bad_digest_when_the_schema_runs_then_it_refuses(
    digest: str,
) -> None:
    result = worker("environment=production", f"image.digest={digest}")

    assert result.returncode != 0
    assert "digest" in result.stderr


@needs_helm
def test_given_worker_values_with_production_and_a_digest_when_templated_then_the_image_is_the_digest() -> None:
    result = worker("environment=production", f"image.digest={DIGEST}")

    assert result.returncode == 0, result.stderr
    assert f"@{DIGEST}" in result.stdout


def test_given_the_worker_chart_defaults_when_read_then_the_environment_is_production() -> None:
    values = yaml.safe_load((WORKER_CHART / "values.yaml").read_text(encoding="utf-8"))

    assert values["environment"] == "production"


@needs_helm
def test_given_the_local_worker_values_when_templated_and_linted_then_they_need_no_digest() -> None:
    local = yaml.safe_load(WORKER_LOCAL.read_text(encoding="utf-8"))

    assert local["environment"] in {"development", "test"}
    assert "digest" not in local.get("image", {})
    for command in ("template", "lint"):
        result = worker(command=command)
        assert result.returncode == 0, result.stdout + result.stderr


@needs_helm
@pytest.mark.parametrize("environment", ["local", "prod", "Production"])
def test_given_a_worker_environment_the_agent_does_not_know_when_templated_then_the_schema_refuses(
    environment: str,
) -> None:
    result = worker(f"environment={environment}", f"image.digest={DIGEST}")

    assert result.returncode != 0
    assert "environment" in result.stderr


@needs_helm
@pytest.mark.parametrize("key", ["ENVIRONMENT", "DATABASE_SSL", "DATABASE_CA_FILE"])
def test_given_worker_env_with_a_chart_owned_key_when_templated_then_it_still_fails(key: str) -> None:
    result = worker(set_env("env", key, "x"))

    assert result.returncode != 0
    assert key in result.stderr
