"""U-web-settings-40: the `app` chart ingress is local only (ADR-0037; AC-16, AC-18, AC-19; W-6, W-9, W-17)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
CHART = ROOT / "deploy" / "charts" / "app"
LOCAL_VALUES = ROOT / "deploy" / "envs" / "local" / "values.yaml"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
HIDDEN_PATHS = ("/docs", "/openapi.json", "/healthz", "/readyz", "/metrics")
# The chart defaults name no proxy (U-web-settings-52): an environment sets them while the ingress is enabled.
PROXY = "api.config.trustedProxyCidrs={10.244.0.0/16}"
# Rendering the bare defaults: the environment must say it is not production (no digest, no alert) and name an HSTS key.
BARE = ("environment=local", "ingress.hstsAnnotation.key=example.test/hsts")


def helm(command: str, *args: str, values: bool = True) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    base = [HELM, command, "app", str(CHART)] if command == "template" else [HELM, command, str(CHART)]
    if command == "lint":
        base.append("--strict")
    if values:
        base += ["-f", str(LOCAL_VALUES)]
    for item in args:
        base += ["--set", item]
    return subprocess.run(base, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def render(*sets: str, values: bool = True) -> list[dict[str, Any]]:
    result = helm("template", *sets, values=values)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def ingress(*sets: str, values: bool = True) -> dict[str, Any]:
    return next(doc for doc in render(*sets, values=values) if doc["kind"] == "Ingress")


def local_ingress_values() -> dict[str, Any]:
    return yaml.safe_load(LOCAL_VALUES.read_text(encoding="utf-8"))["ingress"]


@needs_helm
def test_given_the_rendered_ingress_when_read_then_only_api_auth_and_web_are_routed() -> None:
    rule = ingress()["spec"]["rules"][0]
    routes = [(p["path"], p["backend"]["service"]["name"]) for p in rule["http"]["paths"]]

    assert routes == [("/api", "app-api"), ("/auth", "app-api"), ("/", "app-web")]
    assert not any(path in HIDDEN_PATHS for path, _ in routes)
    assert len(ingress()["spec"]["rules"]) == 1


@needs_helm
def test_given_the_rendered_ingress_when_read_then_tls_redirect_issuer_and_hsts_are_set() -> None:
    spec = ingress()
    annotations = spec["metadata"]["annotations"]
    host = local_ingress_values()["host"]
    header = " ".join(str(value) for value in annotations.values() if "Strict-Transport-Security" in str(value))

    assert spec["spec"]["tls"] == [{"hosts": [host], "secretName": "app-tls"}]
    assert annotations["cert-manager.io/cluster-issuer"] == local_ingress_values()["clusterIssuer"]
    assert annotations["nginx.ingress.kubernetes.io/ssl-redirect"] == "true"
    assert annotations["nginx.ingress.kubernetes.io/force-ssl-redirect"] == "true"
    assert "max-age=31536000" in header
    assert "includeSubDomains" not in header
    assert "preload" not in header


@needs_helm
def test_given_the_hsts_setting_when_the_chart_is_rendered_then_it_is_the_only_source_of_the_header() -> None:
    annotations = ingress("ingress.hsts=true")["metadata"]["annotations"]

    assert any("Strict-Transport-Security" in str(value) for value in annotations.values())
    assert "includeSubDomains" not in str(annotations)


@needs_helm
def test_given_the_local_values_when_linted_strictly_then_the_chart_has_no_findings() -> None:
    result = helm("lint")

    assert result.returncode == 0, result.stdout + result.stderr


@needs_helm
@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("ingress.tls.enabled=false", "tls"),
        ("ingress.hsts=false", "hsts"),
        ("ingress.host=app.example.com", "host"),
        ("ingress.host=app.localhost.example.com", "host"),
        ("ingress.host=localhost", "host"),
        ("ingress.localDomainSuffix=com", "localDomainSuffix"),
        ("ingress.clusterIssuer=letsencrypt-prod", "clusterIssuer"),
    ],
)
def test_given_a_values_file_that_weakens_tls_or_goes_public_when_linted_then_it_fails(
    setting: str, expected: str
) -> None:
    result = helm("lint", setting)

    assert result.returncode != 0, setting
    assert expected in result.stdout + result.stderr


@needs_helm
def test_given_the_local_values_when_rendered_then_the_body_cap_tls_minimum_and_log_format_come_from_values() -> None:
    values = local_ingress_values()
    annotations = ingress()["metadata"]["annotations"]
    config = values["controllerConfig"]

    assert annotations["nginx.ingress.kubernetes.io/proxy-body-size"] == "8k"
    assert config["ssl-protocols"] == "TLSv1.2 TLSv1.3"
    log_format = config["log-format-upstream"]
    assert "$uri" in log_format
    assert not re.search(r"\$(request|request_uri|args|query_string|is_args)\b", log_format)


@needs_helm
def test_given_the_chart_defaults_when_rendered_then_no_controller_specific_annotation_exists() -> None:
    annotations = ingress(PROXY, *BARE, values=False)["metadata"]["annotations"]

    assert set(annotations) == {"cert-manager.io/cluster-issuer", "example.test/hsts"}


def values_files() -> list[Path]:
    deploy = ROOT / "deploy"
    return [
        *deploy.glob("charts/*/values.yaml"),
        *deploy.glob("envs/**/*.yaml"),
    ]


def test_given_the_values_files_when_searched_then_nothing_exposes_a_service_outside_the_cluster() -> None:
    files = values_files()
    assert LOCAL_VALUES in files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"LoadBalancer|nodePort|externalIPs", text, re.IGNORECASE), path


@needs_helm
def test_given_the_rendered_chart_when_read_then_every_service_is_cluster_internal() -> None:
    services = [doc for doc in render() if doc["kind"] == "Service"]

    assert {doc["metadata"]["name"] for doc in services} == {"app-api", "app-web"}
    for doc in services:
        assert doc["spec"].get("type", "ClusterIP") == "ClusterIP"
        assert "externalIPs" not in doc["spec"]
        assert all("nodePort" not in port for port in doc["spec"]["ports"])


def test_given_the_values_files_when_read_then_no_public_host_name_is_set() -> None:
    public = re.compile(r"^\s*host:\s*\S+\.(com|net|org|io|me|dev|app)\s*$", re.MULTILINE)

    for path in values_files():
        assert not public.search(path.read_text(encoding="utf-8")), path


@needs_helm
@pytest.mark.skipif(shutil.which("kubeconform") is None, reason="kubeconform is not installed (CI runs it)")
def test_given_the_rendered_chart_when_checked_with_kubeconform_then_it_passes() -> None:
    manifests = helm("template").stdout
    result = subprocess.run(  # noqa: S603
        [shutil.which("kubeconform") or "", "-strict", "-summary", "-"],
        input=manifests,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@needs_helm
@pytest.mark.skipif(shutil.which("kube-linter") is None, reason="kube-linter is not installed (CI runs it)")
def test_given_the_rendered_chart_when_checked_with_kube_linter_then_it_passes(tmp_path: Path) -> None:
    rendered = tmp_path / "render.yaml"
    rendered.write_text(helm("template").stdout, encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [shutil.which("kube-linter") or "", "lint", str(rendered)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
