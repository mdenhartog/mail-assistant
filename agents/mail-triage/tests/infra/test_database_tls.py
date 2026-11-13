"""U-web-settings-58: verify-full database TLS in the worker chart, pg_hba.conf, compose and CI (SEC-10, W-8, W-9).

The worker chart carries the CA and the setting for the runtime and the migrate job; the prod-like database accepts
every role over TLS only; every consumer of the new settings is wired in the same change.
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
CHART = ROOT / "deploy" / "charts" / "worker"
LOCAL_VALUES = ROOT / "deploy" / "envs" / "local" / "mail-triage.yaml"
PG_HBA = ROOT / "deploy" / "prod-like" / "pg_hba.conf"
COMPOSE = ROOT / "agents" / "mail-triage" / "compose.yaml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
BASE = ("image.repository=registry.example/mail-triage", "migration.secretName=mail-triage-migration")
CA_CONFIG_MAP = "database.tls.caConfigMap=mail-triage-db-ca"


def render(*sets: str, values: Path | None = LOCAL_VALUES) -> list[dict[str, Any]]:
    assert HELM is not None
    command = [HELM, "template", "mail-triage", str(CHART)]
    if values is not None:
        command += ["-f", str(values)]
    for item in (*BASE, *sets):
        command += ["--set", item]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)  # noqa: S603
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def render_fails(*sets: str) -> str:
    assert HELM is not None
    command = [HELM, "template", "mail-triage", str(CHART), "-f", str(LOCAL_VALUES)]
    for item in (*BASE, *sets):
        command += ["--set", item]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)  # noqa: S603
    assert result.returncode != 0, "the chart rendered but must refuse"
    return result.stderr


def pod_spec(docs: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    document = next(doc for doc in docs if doc["kind"] == kind)
    return document["spec"]["template"]["spec"]


def env_of(spec: dict[str, Any]) -> dict[str, str]:
    return {item["name"]: item.get("value", "") for item in spec["containers"][0].get("env", [])}


# -- worker chart --------------------------------------------------------------------------------------------------


@needs_helm
@pytest.mark.parametrize("kind", ["Deployment", "Job"])
def test_given_the_local_values_when_rendered_then_runtime_and_migrate_job_have_the_ca_and_verify_full(
    kind: str,
) -> None:
    spec = pod_spec(render(), kind)
    env = env_of(spec)

    assert env["DATABASE_SSL"] == "verify-full"
    assert env["ENVIRONMENT"] == "production"
    ca_path = env["DATABASE_CA_FILE"]
    mounts = spec["containers"][0]["volumeMounts"]
    mount = next(item for item in mounts if ca_path.startswith(item["mountPath"].rstrip("/") + "/"))
    assert mount["readOnly"] is True
    volume = next(item for item in spec["volumes"] if item["name"] == mount["name"])
    assert volume["configMap"]["name"] == "mail-triage-db-ca"
    assert volume["configMap"]["items"] == [{"key": "ca.crt", "path": ca_path.rsplit("/", 1)[1]}]


@needs_helm
def test_given_no_sslmode_in_the_values_when_rendered_then_the_default_is_verify_full() -> None:
    docs = render(CA_CONFIG_MAP, values=None)

    assert env_of(pod_spec(docs, "Deployment"))["DATABASE_SSL"] == "verify-full"


@needs_helm
def test_given_production_and_a_weaker_sslmode_when_rendered_then_the_chart_refuses() -> None:
    error = render_fails("environment=production", "database.tls.sslMode=require")

    assert "verify-full" in error


@needs_helm
def test_given_production_without_a_ca_when_rendered_then_the_chart_refuses_naming_the_value() -> None:
    error = render_fails("database.tls.caConfigMap=")

    assert "database.tls.caConfigMap" in error


@needs_helm
def test_given_a_development_environment_when_rendered_then_a_weaker_sslmode_is_allowed() -> None:
    docs = render("environment=development", "database.tls.sslMode=disable", "database.tls.caConfigMap=")

    assert env_of(pod_spec(docs, "Deployment"))["DATABASE_SSL"] == "disable"
    assert "DATABASE_CA_FILE" not in env_of(pod_spec(docs, "Deployment"))


@needs_helm
def test_given_a_tls_setting_in_the_plain_env_when_rendered_then_the_chart_refuses() -> None:
    error = render_fails("env.DATABASE_SSL=disable")

    assert "DATABASE_SSL" in error


@needs_helm
def test_given_the_rendered_chart_when_searched_then_no_database_url_or_password_is_in_it() -> None:
    assert HELM is not None
    result = subprocess.run(  # noqa: S603
        [HELM, "template", "mail-triage", str(CHART), "-f", str(LOCAL_VALUES), *[a for s in BASE for a in ("--set", s)]],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )

    assert not re.search(r"postgres(ql)?(\+\w+)?://", result.stdout)


# -- pg_hba.conf, compose, CI --------------------------------------------------------------------------------------


def hba_rules() -> list[list[str]]:
    lines = [line.split("#")[0].split() for line in PG_HBA.read_text(encoding="utf-8").splitlines()]
    return [fields for fields in lines if fields]


def test_given_pg_hba_when_read_then_every_network_rule_is_hostssl_or_a_reject() -> None:
    network = [rule for rule in hba_rules() if rule[0] in {"host", "hostssl", "hostnossl", "hostgssenc"}]

    assert network, "no network rule at all"
    assert [rule for rule in network if rule[0] == "host"] == []  # `host` also matches a plain connection
    assert [rule for rule in network if rule[0] == "hostssl"], "no TLS rule"
    reject = [rule for rule in network if rule[0] == "hostnossl"]
    assert reject
    assert all(rule[-1] == "reject" for rule in reject)
    assert all(rule[-1] == "scram-sha-256" for rule in network if rule[0] == "hostssl")


def test_given_pg_hba_when_read_then_a_plain_connection_of_any_role_is_rejected_before_a_password() -> None:
    nossl = next(rule for rule in hba_rules() if rule[0] == "hostnossl")

    assert nossl[1:3] == ["all", "all"]  # every database, every role: no role is named, so none is left out


def test_given_the_agent_compose_file_when_read_then_both_services_set_environment_ssl_and_the_ca() -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]

    for name in ("mail-triage", "mail-triage-migrate"):
        environment = services[name]["environment"]
        assert {"ENVIRONMENT", "DATABASE_SSL", "DATABASE_CA_FILE"} <= set(environment), name
        assert "MAIL_TRIAGE_DATABASE_SSL" in environment["DATABASE_SSL"]
        assert any("deploy/prod-like/certs" in volume and ":ro" in volume for volume in services[name]["volumes"]), name


def test_given_the_ci_prod_like_job_when_read_then_the_migrate_step_runs_in_production_with_verify_full() -> None:
    workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["prod-like"]["steps"]
    migrate = next(step for step in steps if "mail-triage-migrate" in step.get("run", ""))

    assert migrate["env"]["MAIL_TRIAGE_ENVIRONMENT"] == "production"
    assert migrate["env"]["MAIL_TRIAGE_DATABASE_SSL"] == "verify-full"


def test_given_the_prod_like_checks_when_listed_then_the_agent_role_has_a_plain_connection_refusal_check() -> None:
    check = ROOT / "agents" / "mail-triage" / "tests" / "e2e" / "test_agent_role_tls.py"
    text = check.read_text(encoding="utf-8")

    assert "E2E_PROD_LIKE" in text
    assert "mail_triage_runtime" in text
    assert "pg_hba" in text
