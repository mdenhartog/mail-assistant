"""U-18: container, compose service and Helm chart for mail-triage (spec AC-30; docker/compose/kubernetes/helm)."""

from __future__ import annotations

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


def test_given_the_compose_file_when_read_then_it_holds_no_secret_value() -> None:
    text = (COMPONENT / "compose.yaml").read_text(encoding="utf-8")

    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text)
    for line in text.splitlines():
        if re.search(r"(KEY|TOKEN|PASSWORD|SECRET)\w*:", line):
            assert "${" in line, f"secret-looking setting without an environment reference: {line.strip()}"
