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
# Rendering the bare defaults: the environment must say it is not production (no digest, no alert) and name the
# ingress controller (ADR-0040: required, no default).
BARE = ("environment=local", "ingress.controller=traefik")
TRAEFIK = "traefik.ingress.kubernetes.io"
CRDS = "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"


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
    """The HTTPS Ingress (the one with the TLS section)."""
    docs = render(*sets, values=values)
    return next(doc for doc in docs if doc["kind"] == "Ingress" and doc["spec"].get("tls"))


def of_kind(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [doc for doc in docs if doc["kind"] == kind]


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
def test_given_the_rendered_ingress_when_read_then_tls_issuer_and_the_traefik_objects_are_referenced() -> None:
    docs = render()
    spec = ingress()
    annotations = spec["metadata"]["annotations"]
    host = local_ingress_values()["host"]

    assert spec["spec"]["tls"] == [{"hosts": [host], "secretName": "app-tls"}]
    assert annotations["cert-manager.io/cluster-issuer"] == local_ingress_values()["clusterIssuer"]
    assert annotations[f"{TRAEFIK}/router.entrypoints"] == "websecure"
    assert annotations[f"{TRAEFIK}/router.tls"] == "true"
    # every reference is <namespace>-<name>@kubernetescrd and names an object the chart renders
    option = annotations[f"{TRAEFIK}/router.tls.options"]
    assert option.endswith("@kubernetescrd")
    assert option.removesuffix("@kubernetescrd") in {
        f"default-{d['metadata']['name']}" for d in of_kind(docs, "TLSOption")
    }
    refs = annotations[f"{TRAEFIK}/router.middlewares"].split(",")
    middlewares = {f"default-{d['metadata']['name']}@kubernetescrd" for d in of_kind(docs, "Middleware")}
    assert len(refs) == 2
    assert set(refs) <= middlewares


@needs_helm
def test_given_the_rendered_chart_when_read_then_exactly_one_middleware_sends_hsts_without_subdomains() -> None:
    docs = render()
    senders = [d for d in of_kind(docs, "Middleware") if "stsSeconds" in d["spec"].get("headers", {})]

    assert len(senders) == 1
    headers = senders[0]["spec"]["headers"]
    assert headers["stsSeconds"] == 31536000
    assert not headers.get("stsIncludeSubdomains")
    assert not headers.get("stsPreload")
    assert "Strict-Transport-Security" not in str(docs)  # no second source: no hand written header
    assert "includeSubDomains" not in str(docs)
    assert "preload" not in str(docs).lower()


@needs_helm
def test_given_the_rendered_chart_when_read_then_a_redirect_ingress_sends_http_to_https() -> None:
    docs = render()
    redirect = next(d for d in of_kind(docs, "Ingress") if not d["spec"].get("tls"))
    annotations = redirect["metadata"]["annotations"]
    name = annotations[f"{TRAEFIK}/router.middlewares"].split("@")[0].removeprefix("default-")
    middleware = next(d for d in of_kind(docs, "Middleware") if d["metadata"]["name"] == name)

    assert annotations[f"{TRAEFIK}/router.entrypoints"] == "web"
    assert middleware["spec"]["redirectScheme"] == {"scheme": "https", "permanent": True, "port": "8443"}
    assert redirect["spec"]["rules"][0]["host"] == local_ingress_values()["host"]
    assert "cert-manager.io/cluster-issuer" not in annotations


@needs_helm
def test_given_no_local_https_port_when_rendered_then_the_redirect_uses_the_default_https_port() -> None:
    docs = render("ingress.httpsPort=")
    middleware = next(d for d in of_kind(docs, "Middleware") if "redirectScheme" in d["spec"])

    assert middleware["spec"]["redirectScheme"] == {"scheme": "https", "permanent": True}


@needs_helm
def test_given_the_hsts_setting_when_the_chart_is_rendered_then_it_is_the_only_source_of_the_header() -> None:
    docs = render("ingress.hsts=true")

    assert len([d for d in of_kind(docs, "Middleware") if "stsSeconds" in d["spec"].get("headers", {})]) == 1


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
        ("ingress.controller=nginx", "controller"),
        ("ingress.controller=", "controller"),
        ("ingress.hstsAnnotation.key=x", "hstsAnnotation"),
        ("ingress.annotations.a=b", "annotations"),
        ("ingress.controllerConfig.a=b", "controllerConfig"),
        ("ingress.httpsPort=eight", "httpsPort"),
    ],
)
def test_given_a_values_file_that_weakens_tls_or_goes_public_when_linted_then_it_fails(
    setting: str, expected: str
) -> None:
    result = helm("lint", setting)

    assert result.returncode != 0, setting
    assert expected in result.stdout + result.stderr


@needs_helm
def test_given_the_local_values_when_rendered_then_the_body_cap_and_tls_minimum_are_traefik_objects() -> None:
    docs = render()
    limits = [d for d in of_kind(docs, "Middleware") if "buffering" in d["spec"]]
    options = of_kind(docs, "TLSOption")

    assert [d["spec"]["buffering"] for d in limits] == [{"maxRequestBodyBytes": 8192}]
    assert [d["spec"]["minVersion"] for d in options] == ["VersionTLS12"]
    assert not [d for d in options if d["spec"].get("maxVersion")]


@needs_helm
def test_given_the_local_values_when_rendered_then_no_text_of_another_ingress_controller_is_left() -> None:
    docs = render()
    text = yaml.safe_dump([d for d in docs if d["kind"] in {"Ingress", "Middleware", "TLSOption"}])

    assert "nginx" not in text.lower()  # the web image is nginx, but no ingress object speaks its vocabulary
    assert "configuration-snippet" not in text


def test_given_the_repository_when_searched_then_no_chart_or_environment_file_names_ingress_nginx() -> None:
    files = [p for p in (ROOT / "deploy").glob("charts/**/*") if p.is_file()]
    files += list((ROOT / "deploy").glob("envs/**/*.y*ml"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for word in ("ingress-nginx", "nginx.ingress", "configuration-snippet", "hstsannotation", "controllerconfig"):
            assert word not in text, (path.relative_to(ROOT).as_posix(), word)


@needs_helm
def test_given_the_chart_defaults_when_rendered_then_only_cert_manager_and_traefik_annotations_exist() -> None:
    docs = render(PROXY, *BARE, values=False)

    assert of_kind(docs, "Ingress")
    for doc in of_kind(docs, "Ingress"):
        keys = set(doc["metadata"]["annotations"])
        assert all(k == "cert-manager.io/cluster-issuer" or k.startswith(f"{TRAEFIK}/") for k in keys), keys


@needs_helm
def test_given_no_ingress_controller_when_rendered_then_the_schema_names_the_missing_value() -> None:
    result = helm("template", "environment=local", PROXY, values=False)

    assert result.returncode != 0
    assert "controller" in result.stderr


@needs_helm
def test_given_the_ingress_is_off_when_rendered_then_no_traefik_object_exists() -> None:
    docs = render("ingress.enabled=false")

    assert not [d for d in docs if d["kind"] in {"Middleware", "TLSOption", "Ingress"}]


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
        [
            shutil.which("kubeconform") or "",
            "-strict",
            "-summary",
            "-schema-location",
            "default",
            "-schema-location",
            CRDS,
            "-",
        ],
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
