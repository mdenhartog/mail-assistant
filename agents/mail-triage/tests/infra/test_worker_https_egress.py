"""U-mail-categories-31 (SEC-01): the worker's HTTPS egress is an ipBlock with CIDR exceptions, never a bare port (ADR-0049)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
CHART = ROOT / "deploy" / "charts" / "worker"
LOCAL_VALUES = ROOT / "deploy" / "envs" / "local" / "mail-triage.yaml"
PROD_VALUES = ROOT / "deploy" / "envs" / "production" / "mail-triage.yaml"
README = CHART / "README.md"
ADR = ROOT / "docs" / "memory" / "decisions" / "ADR-0049-worker-egress-cidr-exceptions.md"
INDEX = ROOT / "docs" / "memory" / "index.md"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
DIGEST = "sha256:" + "d" * 64
METADATA = "169.254.0.0/16"
BASE = (
    "image.repository=registry.example/mail-triage",
    f"image.digest={DIGEST}",
    "database.tls.caConfigMap=mail-triage-db-ca",
    "migration.enabled=true",
    "migration.secretName=mail-triage-migration",
)


def helm(command: str, *sets: str, values: Path | None = None) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    args = [HELM, command, "mail-triage", str(CHART)] if command == "template" else [HELM, command, str(CHART)]
    if command == "lint":
        args.append("--strict")
    if values is not None:
        args += ["-f", str(values)]
    for item in (*BASE, *sets) if values is None else sets:
        args += ["--set", item]
    return subprocess.run(args, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def render(*sets: str) -> list[dict[str, Any]]:
    result = helm("template", *sets)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def policies(docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {d["metadata"]["name"]: d["spec"] for d in docs if d["kind"] == "NetworkPolicy"}


def https_rules(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in spec["egress"] if any(p["port"] == 443 for p in r.get("ports", []))]


@needs_helm
def test_given_the_rendered_worker_when_read_then_443_is_one_ip_block_with_the_metadata_pod_and_service_exceptions() -> None:
    spec = policies(render())["mail-triage"]
    rules = https_rules(spec)

    assert len(rules) == 1
    assert rules[0]["ports"] == [{"port": 443}]
    assert rules[0]["to"] == [
        {"ipBlock": {"cidr": "0.0.0.0/0", "except": [METADATA, "10.244.0.0/16", "10.96.0.0/16"]}}
    ]


@needs_helm
def test_given_every_policy_when_rendered_then_no_egress_rule_is_without_a_destination() -> None:
    for name, spec in policies(render()).items():
        for rule in spec["egress"]:
            assert rule.get("to"), (name, rule)


@needs_helm
def test_given_other_cidrs_when_rendered_then_the_exceptions_follow_the_values() -> None:
    spec = policies(render("networkPolicy.https.podCidr=10.42.0.0/16", "networkPolicy.https.serviceCidr=10.43.0.0/16"))
    block = https_rules(spec["mail-triage"])[0]["to"][0]["ipBlock"]

    assert block == {"cidr": "0.0.0.0/0", "except": [METADATA, "10.42.0.0/16", "10.43.0.0/16"]}


@needs_helm
def test_given_the_migration_job_when_rendered_then_it_has_no_443_rule_and_no_open_ip_block() -> None:
    migration = [s for n, s in policies(render()).items() if n != "mail-triage"]

    assert len(migration) == 1
    assert not https_rules(migration[0])
    assert "0.0.0.0/0" not in yaml.safe_dump(migration[0])


@needs_helm
@pytest.mark.parametrize("environment", ["production", "development", "test"])
@pytest.mark.parametrize("key", ["podCidr", "serviceCidr"])
@pytest.mark.parametrize("bad", ["", "REQUIRED", "10.0.0.0", "0.0.0.0/0", "10.0.0.0/33", "not-a-cidr"])
def test_given_a_missing_or_wide_cidr_when_linted_then_the_schema_rejects_it(environment: str, key: str, bad: str) -> None:
    result = helm("lint", f"environment={environment}", f"networkPolicy.https.{key}={bad}")

    assert result.returncode != 0, (environment, key, bad)
    assert key in result.stdout + result.stderr


@needs_helm
def test_given_the_production_values_when_read_then_both_cidrs_are_required_and_the_render_refuses() -> None:
    values = yaml.safe_load(PROD_VALUES.read_text(encoding="utf-8"))
    lines = PROD_VALUES.read_text(encoding="utf-8").splitlines()

    assert values["networkPolicy"]["https"] == {"podCidr": "REQUIRED", "serviceCidr": "REQUIRED"}
    assert sum(1 for line in lines if "REQUIRED # REQUIRED" in line and ("podCidr" in line or "serviceCidr" in line)) == 2
    result = helm("template", values=PROD_VALUES)
    assert result.returncode != 0
    assert "podCidr" in result.stderr


@needs_helm
def test_given_the_local_values_when_linted_strict_then_the_chart_has_no_findings_and_sets_both_cidrs() -> None:
    values = yaml.safe_load(LOCAL_VALUES.read_text(encoding="utf-8"))
    result = helm("lint", values=LOCAL_VALUES)

    assert result.returncode == 0, result.stdout + result.stderr
    assert set(values["networkPolicy"]["https"]) == {"podCidr", "serviceCidr"}


def test_given_the_readme_when_read_then_it_explains_the_https_egress_and_the_residual_risk() -> None:
    sections = README.read_text(encoding="utf-8").split("## HTTPS egress", 1)
    assert len(sections) == 2, "a section 'HTTPS egress'"
    body = sections[1].split("\n## ", 1)[0]

    for needle in (
        "ADR-0049",
        "169.254.0.0/16",
        "networkPolicy.https.podCidr",
        "networkPolicy.https.serviceCidr",
        "any public host",
        "egress proxy",
    ):
        assert needle in body, needle


def test_given_adr_0049_when_read_then_it_is_accepted_indexed_and_names_the_residual_risk() -> None:
    text = ADR.read_text(encoding="utf-8")

    assert "id: ADR-0049" in text
    assert "status: accepted" in text
    assert "any public host on 443" in text
    assert "ADR-0049" in INDEX.read_text(encoding="utf-8")
