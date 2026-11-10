"""U-18: container, compose service and Helm chart for mail-triage (spec AC-30; docker/compose/kubernetes/helm)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
COMPONENT = ROOT / "agents" / "mail-triage"
CHART = ROOT / "deploy" / "charts" / "worker"
SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),  # a Telegram bot token
    re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!\$\{)[^@\s]+@"),  # a URL with a literal password
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")


def render(*sets: str) -> list[dict[str, Any]]:
    assert HELM is not None
    command = [HELM, "template", "mail-triage", str(CHART), "--set", "image.repository=registry.example/mail-triage"]
    for item in sets:
        command += ["--set", item]
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)  # noqa: S603
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def kind(docs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(doc for doc in docs if doc["kind"] == name)


def container(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return kind(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]


@needs_helm
def test_given_the_chart_when_linted_then_it_has_no_errors() -> None:
    result = subprocess.run(  # noqa: S603
        [HELM or "", "lint", str(CHART), "--set", "image.repository=registry.example/mail-triage"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@needs_helm
def test_given_the_deployment_when_rendered_then_one_replica_that_is_never_run_twice_at_once() -> None:
    deployment = kind(render(), "Deployment")

    assert deployment["spec"]["replicas"] == 1
    assert deployment["spec"]["strategy"] == {"type": "Recreate"}


@needs_helm
def test_given_the_pod_when_rendered_then_it_is_non_root_read_only_and_without_capabilities() -> None:
    docs = render()
    spec = kind(docs, "Deployment")["spec"]["template"]["spec"]
    security = container(docs)["securityContext"]

    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["runAsUser"] == 10001
    assert spec["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert spec["automountServiceAccountToken"] is False
    assert security["readOnlyRootFilesystem"] is True
    assert security["allowPrivilegeEscalation"] is False
    assert security["capabilities"] == {"drop": ["ALL"]}
    assert {"limits", "requests"} <= set(container(docs)["resources"])


@needs_helm
def test_given_the_chart_when_rendered_then_there_is_no_ingress_and_no_way_in() -> None:
    docs = render()

    kinds = {doc["kind"] for doc in docs}
    assert "Ingress" not in kinds
    assert "Service" not in kinds
    policy = kind(docs, "NetworkPolicy")["spec"]
    assert "Ingress" in policy["policyTypes"]
    assert policy.get("ingress") in ([], None)
    assert "ports" not in container(docs)


@needs_helm
def test_given_the_network_policy_when_rendered_then_egress_is_only_dns_https_and_the_database() -> None:
    policy = kind(render(), "NetworkPolicy")["spec"]

    assert "Egress" in policy["policyTypes"]
    ports = {rule_port["port"] for rule in policy["egress"] for rule_port in rule.get("ports", [])}
    assert ports == {53, 443, 5432}
    assert all(rule.get("to") is not None or rule["ports"] == [{"port": 443}] for rule in policy["egress"])
    database = next(rule for rule in policy["egress"] if {"port": 5432} in rule["ports"])
    assert database["to"] == [{"podSelector": {}}]  # the database in the same namespace, not the world


@needs_helm
def test_given_secrets_when_deployed_then_they_come_from_a_kubernetes_secret_and_not_from_values() -> None:
    docs = render("envFromSecret=mail-triage-secrets", "env.POLL_INTERVAL_SECONDS=60")
    env = container(docs)

    assert env["envFrom"] == [{"secretRef": {"name": "mail-triage-secrets"}}]
    names = {item["name"] for item in env["env"]}
    assert "POLL_INTERVAL_SECONDS" in names
    assert not any(token in name for name in names for token in ("KEY", "TOKEN", "PASSWORD", "SECRET"))


@needs_helm
def test_given_the_worker_when_rendered_then_a_heartbeat_probe_replaces_the_http_probe() -> None:
    probes = container(render())

    assert "exec" in probes["livenessProbe"]
    assert "httpGet" not in probes["livenessProbe"]
    assert "readinessProbe" not in probes


@needs_helm
def test_given_the_rendered_manifests_when_scanned_then_they_contain_no_secret_value() -> None:
    docs = render("envFromSecret=mail-triage-secrets", "env.POLL_INTERVAL_SECONDS=60")
    text = yaml.safe_dump(docs)

    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text), pattern.pattern


def test_given_the_image_when_built_then_it_runs_as_a_numeric_non_root_user() -> None:
    lines = (COMPONENT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    last_stage = lines[max(i for i, line in enumerate(lines) if line.startswith("FROM ")) :]
    users = [line.split()[1] for line in last_stage if line.startswith("USER ")]

    assert users, "the final stage must set a USER"
    uid = users[-1].split(":")[0]
    assert uid.isdigit()
    assert int(uid) != 0


def test_given_the_image_when_built_then_it_carries_the_migrations_the_agent_applies_at_start() -> None:
    text = (COMPONENT / "Dockerfile").read_text(encoding="utf-8")

    assert re.search(r"^COPY agents/mail-triage/migrations \./migrations$", text, re.MULTILINE)


def test_given_the_dockerfile_when_scanned_then_it_has_no_secret_or_env_file() -> None:
    text = (COMPONENT / "Dockerfile").read_text(encoding="utf-8")

    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text)
    assert not re.search(r"^(ARG|ENV)\s+\S*(KEY|TOKEN|SECRET|PASSWORD)", text, re.IGNORECASE | re.MULTILINE)
    assert ".env" not in re.sub(r"\.env\.example", "", text)
    assert "latest" not in text.lower().replace("latest compatible", "")


def test_given_the_compose_service_when_read_then_it_is_hardened_and_starts_with_the_database_in_dev() -> None:
    service = yaml.safe_load((COMPONENT / "compose.yaml").read_text(encoding="utf-8"))["services"]["mail-triage"]

    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert "dev" in service["profiles"]
    assert service["depends_on"]["db"]["condition"] == "service_healthy"
    assert "ports" not in service
    check = service["healthcheck"]["test"]  # guardrail-compose: a healthcheck on every service
    assert check[0] == "CMD"
    assert "/tmp/heartbeat" in " ".join(check)  # noqa: S108 - the container's own tmpfs


def test_given_the_compose_file_when_read_then_it_holds_no_secret_value() -> None:
    text = (COMPONENT / "compose.yaml").read_text(encoding="utf-8")

    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text)
    for line in text.splitlines():
        if re.search(r"(KEY|TOKEN|PASSWORD|SECRET)\w*:", line):
            assert "${" in line, f"secret-looking setting without an environment reference: {line.strip()}"


def test_given_the_image_when_built_from_the_repo_root_then_it_carries_the_shared_schedule_policy_package() -> None:
    text = (COMPONENT / "Dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load((COMPONENT / "compose.yaml").read_text(encoding="utf-8"))
    build = compose["services"]["mail-triage"]["build"]

    assert re.search(r"^COPY packages/schedule-policy/schedule_policy ", text, re.MULTILINE)
    assert (COMPONENT / build["context"]).resolve() == ROOT
    assert build["dockerfile"] == "agents/mail-triage/Dockerfile"


# --- U-quiet-hours-15a: the owner role runs the migrations, the agent runs with a role that owns nothing (ADR-0025) ---

MIGRATION = ("migration.enabled=true", "migration.secretName=mail-triage-migration")
OWNER_KEYS = ("DATABASE_OWNER_URL", "RUNTIME_ROLE_PASSWORD")
COMPOSE_FILE = COMPONENT / "compose.yaml"


def compose_services() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["services"]


def migration_job(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return kind(docs, "Job")


def job_container(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return migration_job(docs)["spec"]["template"]["spec"]["containers"][0]


@needs_helm
def test_given_the_migration_is_off_when_rendered_then_there_is_no_job() -> None:
    assert "Job" not in {doc["kind"] for doc in render()}


@needs_helm
def test_given_the_chart_with_the_migration_when_linted_strictly_then_it_has_no_findings() -> None:
    result = subprocess.run(  # noqa: S603
        [HELM or "", "lint", "--strict", str(CHART), "--set", "image.repository=registry.example/mail-triage"]
        + [arg for item in MIGRATION for arg in ("--set", item)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@needs_helm
def test_given_the_migration_when_rendered_then_the_job_is_a_presync_hook_and_a_helm_pre_hook() -> None:
    annotations = migration_job(render(*MIGRATION))["metadata"]["annotations"]

    assert annotations["argocd.argoproj.io/hook"] == "PreSync"
    assert annotations["argocd.argoproj.io/hook-delete-policy"] == "BeforeHookCreation"
    assert annotations["helm.sh/hook"] == "pre-install,pre-upgrade"
    assert annotations["helm.sh/hook-delete-policy"] == "before-hook-creation"


@needs_helm
def test_given_the_migration_when_rendered_then_the_job_runs_migrate_with_the_owner_secret_by_reference() -> None:
    docs = render(*MIGRATION)
    job = job_container(docs)

    assert job["command"] == ["python", "-m", "app", "migrate"]
    refs = {item["name"]: item["valueFrom"]["secretKeyRef"] for item in job["env"] if "valueFrom" in item}
    assert set(refs) == set(OWNER_KEYS)
    assert {ref["name"] for ref in refs.values()} == {"mail-triage-migration"}
    assert all(item.get("value") is None for item in job["env"] if item["name"] in OWNER_KEYS)
    assert "envFrom" not in job  # the runtime secret is not needed to migrate


@needs_helm
def test_given_the_migration_when_rendered_then_the_runtime_pod_never_references_the_owner_secret() -> None:
    docs = render(*MIGRATION, "envFromSecret=mail-triage-secrets")
    deployment = yaml.safe_dump(kind(docs, "Deployment"))

    assert "mail-triage-migration" not in deployment
    assert not any(key in deployment for key in OWNER_KEYS)
    assert container(docs)["envFrom"] == [{"secretRef": {"name": "mail-triage-secrets"}}]
    assert not any(volume.get("secret") for volume in kind(docs, "Deployment")["spec"]["template"]["spec"]["volumes"])


@needs_helm
def test_given_the_migration_when_rendered_then_the_job_pod_is_hardened_and_bounded() -> None:
    docs = render(*MIGRATION)
    spec = migration_job(docs)["spec"]["template"]["spec"]
    security = job_container(docs)["securityContext"]

    assert spec["restartPolicy"] == "Never"
    assert migration_job(docs)["spec"]["backoffLimit"] <= 3
    assert migration_job(docs)["spec"]["activeDeadlineSeconds"] > 0
    assert migration_job(docs)["spec"]["ttlSecondsAfterFinished"] > 0  # kube-linter: finished Jobs clean themselves up
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["runAsUser"] == 10001
    assert spec["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert spec["automountServiceAccountToken"] is False
    assert security["readOnlyRootFilesystem"] is True
    assert security["allowPrivilegeEscalation"] is False
    assert security["capabilities"] == {"drop": ["ALL"]}
    assert {"limits", "requests"} <= set(job_container(docs)["resources"])
    assert not job_container(docs)["image"].endswith(":latest")


@needs_helm
def test_given_the_migration_when_rendered_then_the_job_pod_may_reach_only_dns_and_the_database() -> None:
    docs = render(*MIGRATION)
    pod_labels = migration_job(docs)["spec"]["template"]["metadata"]["labels"]
    deployment_labels = kind(docs, "Deployment")["spec"]["template"]["metadata"]["labels"]
    policies = [doc for doc in docs if doc["kind"] == "NetworkPolicy"]
    policy = next(p for p in policies if p["spec"]["podSelector"]["matchLabels"].items() <= pod_labels.items())["spec"]

    assert pod_labels["app.kubernetes.io/name"] != deployment_labels["app.kubernetes.io/name"]
    assert policy.get("ingress") in ([], None)
    ports = {rule_port["port"] for rule in policy["egress"] for rule_port in rule.get("ports", [])}
    assert ports == {53, 5432}  # no HTTPS: the migration needs nothing from the internet


@needs_helm
def test_given_the_migration_without_a_secret_name_when_rendered_then_it_fails_naming_the_value() -> None:
    assert HELM is not None
    result = subprocess.run(  # noqa: S603
        [
            HELM,
            "template",
            "mail-triage",
            str(CHART),
            "--set",
            "image.repository=r/x",
            "--set",
            "migration.enabled=true",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode != 0
    assert "migration.secretName" in result.stderr


@needs_helm
def test_given_the_migration_when_rendered_then_the_manifests_and_values_hold_no_secret_value() -> None:
    docs = render(*MIGRATION, "envFromSecret=mail-triage-secrets")
    text = yaml.safe_dump(docs)
    values = (CHART / "values.yaml").read_text(encoding="utf-8")
    env_values = (ROOT / "deploy" / "envs" / "local" / "mail-triage.yaml").read_text(encoding="utf-8")

    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text + values + env_values), pattern.pattern
    assert "mail-triage-migration" in env_values  # a name reference only
    assert not re.search(r"(DATABASE_OWNER_URL|RUNTIME_ROLE_PASSWORD)\s*:\s*\S", values + env_values)


def test_given_the_local_environment_values_when_read_then_the_migration_is_on_by_reference() -> None:
    values = yaml.safe_load((ROOT / "deploy" / "envs" / "local" / "mail-triage.yaml").read_text(encoding="utf-8"))

    assert values["migration"]["enabled"] is True
    assert values["migration"]["secretName"]
    assert values["migration"]["secretName"] != values["envFromSecret"]


def test_given_the_compose_file_when_read_then_a_one_shot_migrate_service_uses_the_owner_url() -> None:
    migrate = compose_services()["mail-triage-migrate"]

    assert migrate["command"] == ["python", "-m", "app", "migrate"]
    assert migrate["restart"] == "no"
    assert migrate["depends_on"]["db"]["condition"] == "service_healthy"
    assert set(migrate["profiles"]) == set(compose_services()["mail-triage"]["profiles"])
    assert migrate["read_only"] is True
    assert migrate["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in migrate["security_opt"]
    assert "ports" not in migrate
    assert set(migrate["environment"]) == set(OWNER_KEYS)
    assert "app:${POSTGRES_PASSWORD" in migrate["environment"]["DATABASE_OWNER_URL"]  # the bootstrap owner of the db


def test_given_the_compose_file_when_read_then_the_agent_waits_for_the_migration_and_runs_as_the_runtime_role() -> None:
    agent = compose_services()["mail-triage"]
    database_url = agent["environment"]["DATABASE_URL"]

    assert agent["depends_on"]["mail-triage-migrate"]["condition"] == "service_completed_successfully"
    assert agent["depends_on"]["db"]["condition"] == "service_healthy"
    assert "//mail_triage_runtime:" in database_url
    assert "//app:" not in database_url
    assert not any("OWNER" in name for name in agent["environment"])


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is needed to render the compose file")
def test_given_the_dev_profile_when_compose_renders_then_the_migration_precedes_the_agent() -> None:
    env = {
        **os.environ,
        "POSTGRES_PASSWORD": "pg-render-test",
        "MAIL_TRIAGE_RUNTIME_PASSWORD": "rt-render-test",
    }
    result = subprocess.run(
        ["docker", "compose", "--profile", "dev", "config", "--format", "json"],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    assert services["mail-triage"]["depends_on"]["mail-triage-migrate"]["condition"] == "service_completed_successfully"
    assert services["mail-triage-migrate"]["environment"]["DATABASE_OWNER_URL"].startswith("postgresql+asyncpg://app:")
    assert "mail_triage_runtime:rt-render-test@" in services["mail-triage"]["environment"]["DATABASE_URL"]
    assert "rt-render-test" not in COMPOSE_FILE.read_text(encoding="utf-8")


def test_given_the_migrate_settings_when_compared_then_the_compose_job_passes_every_one_on() -> None:
    from app.settings import MigrateSettings  # noqa: PLC0415

    environment = compose_services()["mail-triage-migrate"]["environment"]

    assert {name.upper() for name in MigrateSettings.model_fields} <= set(environment)


def test_given_the_image_when_built_then_it_carries_the_grants_the_migration_applies() -> None:
    ignore = (COMPONENT / "Dockerfile.dockerignore").read_text(encoding="utf-8")
    dockerfile = (COMPONENT / "Dockerfile").read_text(encoding="utf-8")

    assert "!agents/mail-triage/app" in ignore
    assert re.search(r"^COPY agents/mail-triage/app \./app$", dockerfile, re.MULTILINE)
    assert (COMPONENT / "app" / "db" / "grants.sql").is_file()
