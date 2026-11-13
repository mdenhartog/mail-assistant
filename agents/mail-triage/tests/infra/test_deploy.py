"""U-18: container, compose service and Helm chart for mail-triage (spec AC-30; docker/compose/kubernetes/helm)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
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
    command = [
        HELM,
        "template",
        "mail-triage",
        str(CHART),
        "--set",
        "image.repository=registry.example/mail-triage",
        "--set",
        "database.tls.caConfigMap=mail-triage-db-ca",
    ]
    command += ["--set", "database.tls.caConfigMap=mail-triage-db-ca"]  # production needs the CA (SEC-10)
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
        [
            HELM or "",
            "lint",
            str(CHART),
            "--set",
            "image.repository=registry.example/mail-triage",
            "--set",
            "database.tls.caConfigMap=mail-triage-db-ca",
        ],
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
OWNER_KEYS = ("DATABASE_OWNER_URL", "RUNTIME_ROLE_PASSWORD", "WEB_ROLE_PASSWORD")
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
        [
            HELM or "",
            "lint",
            "--strict",
            str(CHART),
            "--set",
            "image.repository=registry.example/mail-triage",
            "--set",
            "database.tls.caConfigMap=mail-triage-db-ca",
        ]
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
            "database.tls.caConfigMap=mail-triage-db-ca",
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
    assert not re.search(r"(DATABASE_OWNER_URL|RUNTIME_ROLE_PASSWORD|WEB_ROLE_PASSWORD)\s*:\s*\S", values + env_values)


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
    assert set(migrate["environment"]) == {*OWNER_KEYS, "ENVIRONMENT", "DATABASE_SSL", "DATABASE_CA_FILE"}
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
        "WEB_ROLE_PASSWORD": "web-render-test",
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
    assert services["mail-triage-migrate"]["environment"]["WEB_ROLE_PASSWORD"] == "web-render-test"  # noqa: S105
    assert "rt-render-test" not in COMPOSE_FILE.read_text(encoding="utf-8")
    assert "web-render-test" not in COMPOSE_FILE.read_text(encoding="utf-8")


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


# --- U-quiet-hours-15b: CI migrates apart from `up --wait`, checks the runtime role and scans the image (AC-30) ---

CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def ci_jobs() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def run_steps(job: dict[str, Any]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is needed to render the compose file")
def test_given_the_prod_like_profile_when_compose_renders_then_it_holds_no_one_shot_service() -> None:
    # `up --wait` treats a container that exited (even with 0) as a failure, so the one-shot migrate stays out of it
    env = {**os.environ, "POSTGRES_PASSWORD": "pg-render-test"}
    result = subprocess.run(
        ["docker", "compose", "--profile", "prod-like", "config", "--format", "json"],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    assert "mail-triage-migrate" not in services
    assert "mail-triage" not in services  # the agent needs real Gmail, Telegram and Anthropic credentials


def test_given_the_ci_workflow_when_read_then_one_prod_like_job_replaces_the_e2e_and_runtime_role_jobs() -> None:
    jobs = ci_jobs()

    assert "prod-like" in jobs
    assert "e2e" not in jobs
    assert "runtime-role" not in jobs


def test_given_the_prod_like_job_when_read_then_it_runs_the_stated_sequence_once() -> None:
    commands = run_steps(ci_jobs()["prod-like"])
    in_order = [
        "up -d --wait db mail",  # the database and the mail catcher first
        # then the migration, apart from `up --wait`, over verify-full TLS as in production (U-web-settings-58)
        "docker compose run --rm --build -e ENVIRONMENT=production -e DATABASE_SSL=verify-full mail-triage-migrate",
        "docker compose --profile prod-like up -d --build --wait",
        "readyz",
        "backend/tests/e2e",  # TLS database, mail catcher, log canaries
        "agents/mail-triage/tests/e2e",  # the agent role and the web role
        "pnpm --filter web e2e",  # setup project, smoke test
        "scripts/prodlike-checks.sh logs",  # the log grep comes last
    ]
    positions = [commands.index(part) for part in in_order]

    assert positions == sorted(positions)
    assert commands.count("mail-triage-migrate") == 1
    assert "MAIL_TRIAGE_RUNTIME_PASSWORD=" in commands  # the migrate job stops without it (exit code 2)
    assert "WEB_ROLE_PASSWORD=" in commands  # the job stops without this one too (U-web-settings-08)


def test_given_the_prod_like_job_when_it_ends_then_the_reports_and_logs_are_uploaded_and_stack_goes_down() -> None:
    steps = ci_jobs()["prod-like"]["steps"]
    uploads = [step for step in steps if "upload-artifact" in str(step.get("uses", ""))]

    assert {step["with"]["name"] for step in uploads} == {"playwright-report", "prod-like-logs"}
    assert all(step.get("if") in {"failure()", "always()"} for step in uploads)
    assert any("down --volumes" in str(step.get("run", "")) and step.get("if") == "always()" for step in steps)


def test_given_the_prod_like_job_when_the_migration_fails_then_it_stops_before_the_stack_and_keeps_the_log() -> None:
    steps = ci_jobs()["prod-like"]["steps"]
    migrate = next(i for i, step in enumerate(steps) if "mail-triage-migrate" in str(step.get("run", "")))
    up = next(i for i, step in enumerate(steps) if "up -d --build --wait" in str(step.get("run", "")))
    uploads = [step for step in steps if "prod-like-logs" in str(step.get("with", ""))]

    assert migrate < up  # a failed migration stops the job before the stack is started
    assert "set -o pipefail" in steps[migrate]["run"]  # the pipe into tee must not hide the failure
    assert "prodlike-logs/migrate.log" in steps[migrate]["run"]
    assert [step["with"]["path"] for step in uploads] == ["prodlike-logs"]  # the log is uploaded from a failed run


def test_given_the_gxp_job_when_read_then_it_does_not_run_the_migration() -> None:
    assert "mail-triage-migrate" not in run_steps(ci_jobs()["gxp"])


def test_given_the_ci_workflow_when_read_then_the_mail_triage_image_is_scanned_for_high_and_critical() -> None:
    commands = run_steps(ci_jobs()["components"])

    assert "agents/mail-triage" in commands
    assert "aquasec/trivy" in commands
    assert "--exit-code 1" in commands
    assert "--severity HIGH,CRITICAL" in commands


def test_given_the_repository_when_searched_then_no_scan_ignores_findings() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "--skip-" not in workflow
    assert "--ignorefile" not in workflow
    assert "trivyignore" not in workflow
    assert not list(ROOT.glob(".trivyignore*"))
    assert not (ROOT / "trivy.yaml").exists()


# --- U-quiet-hours-16f: CI for the shared package and the nightly mutation gate (ADR-0030 item 4) ---

PACKAGE_DIR = "packages/schedule-policy"
MUTATION_WORKFLOW = ROOT / ".github" / "workflows" / "mutation.yml"
PINNED_ACTION = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def load_workflow(path: Path) -> dict[str, Any]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    workflow["on"] = workflow.pop(True, workflow.get("on"))  # YAML 1.1 reads the key `on` as True
    return workflow


def package_job() -> dict[str, Any]:
    jobs = ci_jobs()
    assert "schedule-policy" in jobs
    return jobs["schedule-policy"]


def test_given_the_ci_workflow_when_read_then_a_job_checks_the_shared_package_in_its_own_directory() -> None:
    job = package_job()
    commands = run_steps(job).splitlines()

    assert job["defaults"]["run"]["working-directory"] == PACKAGE_DIR
    for command in (
        "uv sync --frozen",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run pyright",
        "uv run pytest",
        "uv run pip-audit",
    ):
        assert command in commands


def test_given_the_shared_package_when_configured_then_pyright_and_pip_audit_are_available_to_the_ci_job() -> None:
    pyproject = (ROOT / PACKAGE_DIR / "pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.pyright]" in pyproject  # the job runs pyright because the package configures it
    assert re.search(r'"pip-audit>=', pyproject)
    assert "pip-audit" in (ROOT / PACKAGE_DIR / "uv.lock").read_text(encoding="utf-8")


def test_given_the_ci_workflow_when_read_then_the_package_job_sets_up_uv_like_the_other_jobs() -> None:
    uses = [step["uses"] for step in package_job()["steps"] if "uses" in step]

    assert any(use.startswith("actions/checkout@") for use in uses)
    assert any(use.startswith("astral-sh/setup-uv@") for use in uses)


def test_given_the_mutation_workflow_when_read_then_it_runs_only_nightly_and_by_hand() -> None:
    workflow = load_workflow(MUTATION_WORKFLOW)

    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    assert workflow["on"]["schedule"][0]["cron"]
    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        assert "permissions" not in job or job["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("directory", ["agents/mail-triage", PACKAGE_DIR])
def test_given_the_mutation_workflow_when_read_then_each_module_is_mutated_and_rated_at_85_percent(
    directory: str,
) -> None:
    jobs = [
        job
        for job in load_workflow(MUTATION_WORKFLOW)["jobs"].values()
        if job.get("defaults", {}).get("run", {}).get("working-directory") == directory
    ]

    assert len(jobs) == 1
    commands = run_steps(jobs[0])
    assert "uv sync --frozen" in commands
    assert re.search(r"uv run cosmic-ray init cosmic-ray\.toml \S+", commands)
    assert re.search(r"uv run cosmic-ray exec cosmic-ray\.toml \S+", commands)
    assert re.search(r"uv run cr-rate \S+ --fail-over 15\b", commands)  # at most 15 % survivors = score >= 85 %
    assert commands.index("cosmic-ray init") < commands.index("cosmic-ray exec") < commands.index("cr-rate")
    assert (ROOT / directory / "cosmic-ray.toml").is_file()


RATING = re.compile(r"cr-rate|mutation/run\.py")


def test_given_the_mutation_workflow_when_a_job_fails_then_the_surviving_mutants_are_still_listed() -> None:
    for name, job in load_workflow(MUTATION_WORKFLOW)["jobs"].items():
        steps = job["steps"]
        if name == "backend-matrix":  # only lists the modules for the backend jobs
            continue
        # the backend runner (backend/mutation/run.py) rates every module itself with cr-rate
        rate = next(i for i, step in enumerate(steps) if RATING.search(step.get("run", "")))
        report = next(i for i, step in enumerate(steps) if "cr-report" in step.get("run", ""))

        assert report > rate, name  # after the rating, so a failing rating does not hide the list
        assert steps[report].get("if") == "always()", name
        assert "--surviving-only" in steps[report]["run"], name
        assert "--show-diff" in steps[report]["run"], name


def test_given_the_workflows_when_read_then_every_action_is_pinned_by_commit_sha() -> None:
    for path in (CI_WORKFLOW, MUTATION_WORKFLOW):
        workflow = load_workflow(path)
        uses = [step["uses"] for job in workflow["jobs"].values() for step in job["steps"] if "uses" in step]

        assert uses, path.name
        assert all(PINNED_ACTION.match(use) for use in uses), (path.name, uses)


def test_given_the_mutation_workflow_when_read_then_every_job_has_a_timeout() -> None:
    for job in load_workflow(MUTATION_WORKFLOW)["jobs"].values():
        assert isinstance(job.get("timeout-minutes"), int)


# --- U-quiet-hours-16e: policy and ServiceAccount exist before the Job, sealing by stdin, tzdata from the wheel ---

README = CHART / "README.md"
HOOK_KEYS = ("argocd.argoproj.io/hook", "helm.sh/hook")


def migration_policy(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return next(doc for doc in docs if doc["kind"] == "NetworkPolicy" and doc["metadata"]["name"].endswith("-migrate"))


def migration_account(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return next(doc for doc in docs if doc["kind"] == "ServiceAccount" and doc["metadata"]["name"].endswith("-migrate"))


@needs_helm
@pytest.mark.parametrize("resource", [migration_policy, migration_account])
def test_given_the_migration_when_rendered_then_the_policy_and_account_are_hooks_created_before_the_job(
    resource: Any,
) -> None:
    docs = render(*MIGRATION)
    job = migration_job(docs)["metadata"]["annotations"]
    annotations = resource(docs)["metadata"]["annotations"]

    for key in HOOK_KEYS:
        assert annotations[key] == job[key]
    assert int(annotations["helm.sh/hook-weight"]) < int(job.get("helm.sh/hook-weight", "0"))
    assert int(annotations["argocd.argoproj.io/sync-wave"]) < int(job.get("argocd.argoproj.io/sync-wave", "0"))
    assert annotations["argocd.argoproj.io/hook-delete-policy"] == "BeforeHookCreation"
    assert annotations["helm.sh/hook-delete-policy"] == "before-hook-creation"


@needs_helm
def test_given_the_migration_when_rendered_then_the_job_has_its_own_account_without_a_token() -> None:
    docs = render(*MIGRATION)
    spec = migration_job(docs)["spec"]["template"]["spec"]
    account = migration_account(docs)
    worker_account = kind(docs, "Deployment")["spec"]["template"]["spec"]["serviceAccountName"]

    assert spec["serviceAccountName"] == account["metadata"]["name"]
    assert spec["serviceAccountName"] != worker_account
    assert account["automountServiceAccountToken"] is False
    assert spec["automountServiceAccountToken"] is False


@needs_helm
def test_given_the_migration_is_off_when_rendered_then_there_is_no_migrate_account_or_policy() -> None:
    docs = render()

    assert not [doc for doc in docs if doc["metadata"]["name"].endswith("-migrate")]


def test_given_the_readme_when_read_then_secret_keys_are_never_passed_with_from_literal() -> None:
    text = README.read_text(encoding="utf-8")

    assert "--from-literal=" not in text  # a value on the command line lands in shell history and the process list
    assert "--from-env-file=/dev/stdin" in text
    assert "kubeseal" in text


def dockerfile_runtime_env() -> dict[str, str]:
    lines = (COMPONENT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    stage = lines[max(i for i, line in enumerate(lines) if line.startswith("FROM ")) :]
    env: dict[str, str] = {}
    for line in stage:
        if line.startswith("ENV "):
            for name, value in re.findall(r'(\w+)=("[^"]*"|\S*)', line[4:]):
                env[name] = value.strip('"')
    return env


def test_given_the_runtime_image_when_zoneinfo_resolves_then_no_system_zoneinfo_directory_can_win() -> None:
    # python:*-slim-bookworm is Debian and may ship /usr/share/zoneinfo; zoneinfo reads TZPATH before the tzdata wheel.
    env = dockerfile_runtime_env()

    assert "PYTHONTZPATH" in env, "set PYTHONTZPATH so that the pinned tzdata wheel is the only source (ADR-0028)"
    probe = (
        "import zoneinfo, pathlib, tzdata;"
        "assert all(not pathlib.Path(p).is_dir() for p in zoneinfo.TZPATH), zoneinfo.TZPATH;"
        "zoneinfo.ZoneInfo('Europe/Amsterdam')"
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


def test_given_the_runtime_image_when_read_then_tzdata_is_a_locked_dependency_of_the_agent() -> None:
    lock = (COMPONENT / "uv.lock").read_text(encoding="utf-8")

    assert re.search(r'^name = "tzdata"$', lock, re.MULTILINE)


# --- U-web-settings-08: the web role password reaches the migrate job everywhere it runs ---


def test_given_the_compose_file_when_read_then_the_migrate_service_passes_the_web_password_by_reference() -> None:
    environment = compose_services()["mail-triage-migrate"]["environment"]

    assert environment["WEB_ROLE_PASSWORD"] == "${WEB_ROLE_PASSWORD:-}"  # noqa: S105  # a reference, empty when unset (exit code 2)
    assert "WEB_ROLE_PASSWORD" not in compose_services()["mail-triage"]["environment"]  # the agent never needs it


@needs_helm
def test_given_the_migration_when_rendered_then_the_web_password_is_a_required_secret_key_reference() -> None:
    job = job_container(render(*MIGRATION))

    ref = next(item for item in job["env"] if item["name"] == "WEB_ROLE_PASSWORD")["valueFrom"]["secretKeyRef"]
    assert ref == {"name": "mail-triage-migration", "key": "WEB_ROLE_PASSWORD"}  # no `optional`: a missing key fails


def test_given_the_chart_files_when_read_then_the_web_password_is_in_no_values_file_or_configmap() -> None:
    values = (CHART / "values.yaml").read_text(encoding="utf-8")
    env_values = (ROOT / "deploy" / "envs" / "local" / "mail-triage.yaml").read_text(encoding="utf-8")

    assert not re.search(r"WEB_ROLE_PASSWORD\s*:\s*\S", values + env_values)
    assert not (CHART / "templates" / "configmap.yaml").exists() or "WEB_ROLE_PASSWORD" not in (
        CHART / "templates" / "configmap.yaml"
    ).read_text(encoding="utf-8")


def test_given_the_chart_readme_when_read_then_it_names_the_web_password_key_and_seals_by_standard_input() -> None:
    text = README.read_text(encoding="utf-8")

    assert "WEB_ROLE_PASSWORD" in text
    assert "--from-literal=" not in text
    assert "--from-env-file=/dev/stdin" in text


# --- U-web-settings-49: the purge runs inside the migrate Job; nothing else holds the owner secret (AC-21, W-13) ---


@needs_helm
def test_given_the_chart_when_searched_then_no_cron_job_and_only_the_migrate_job_holds_the_owner_secret() -> None:
    docs = render(*MIGRATION, "envFromSecret=mail-triage-secrets")

    assert "CronJob" not in {doc["kind"] for doc in docs}
    holders = [doc for doc in docs if "mail-triage-migration" in yaml.safe_dump(doc)]
    assert [(doc["kind"], doc["metadata"]["name"]) for doc in holders] == [
        ("Job", migration_job(docs)["metadata"]["name"])
    ]
    for doc in docs:
        if doc["kind"] != "Job":
            assert not any(key in yaml.safe_dump(doc) for key in OWNER_KEYS)
    assert job_container(docs)["command"] == ["python", "-m", "app", "migrate"]  # the purge is a step of this command
