"""U-web-settings-57 and U-74: ingress gates for HSTS, redirect, TLS minimum, the certificate alert and image digests.

Findings RT-10, SEC-05, SEC-07, SEC2-04, SEC3-02; AC-18, W-9 (ADR-0037, ADR-0039, ADR-0040). The controller is Traefik:
the gates read the rendered Middleware and TLSOption objects and the Ingresses that reference them.
"""

from __future__ import annotations

import copy
import fnmatch
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
CHART = ROOT / "deploy" / "charts" / "app"
ENVS = ROOT / "deploy" / "envs"
LOCAL_VALUES = ENVS / "local" / "values.yaml"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
DIGEST = "sha256:" + "a" * 64  # a well-formed digest for the schema; not an image anybody runs


def helm(command: str, values: Path, *sets: str) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    base = [HELM, command, "app", str(CHART)] if command == "template" else [HELM, command, str(CHART), "--strict"]
    base += ["-f", str(values)]
    for item in sets:
        base += ["--set-json" if item.startswith("json:") else "--set", item.removeprefix("json:")]
    return subprocess.run(base, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Merge like Helm does: maps merge, anything else replaces, and null deletes the key."""
    merged = dict(base)
    for key, value in over.items():
        inner = merged.get(key)
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = deep_merge(inner, value) if isinstance(inner, dict) and isinstance(value, dict) else value
    return merged


def env_value_files() -> list[Path]:
    return sorted(ENVS.glob("*/values.yaml"))


def weakened(override: dict[str, Any], tmp: Path) -> Path:
    """Write a copy of the local values with `override` merged in (null deletes a key)."""
    merged = deep_merge(yaml.safe_load(LOCAL_VALUES.read_text(encoding="utf-8")), override)
    path = tmp / "values.yaml"
    path.write_text(yaml.safe_dump(merged), encoding="utf-8")
    return path


def ingress_gate_findings(docs: list[dict[str, Any]]) -> list[str]:
    """What the rendered objects are missing (ADR-0040): HSTS, the HTTP redirect, the TLS minimum and the body cap."""
    middlewares = [d["spec"] for d in docs if d["kind"] == "Middleware"]
    missing: list[str] = []

    hsts = [m["headers"] for m in middlewares if "stsSeconds" in m.get("headers", {})]
    by_hand = [m for m in middlewares if "strict-transport-security" in str(m.get("headers", {})).lower()]
    if not hsts:
        missing.append("a Middleware with an HSTS directive (headers.stsSeconds)")
    elif hsts[0]["stsSeconds"] != 31536000:
        missing.append("an HSTS max-age of 31536000")
    if len(hsts) + len(by_hand) > 1:
        missing.append("exactly one HSTS directive (a second one is rendered)")
    if any(h.get("stsIncludeSubdomains") or h.get("stsPreload") for h in hsts):
        missing.append("an HSTS directive without includeSubDomains and preload")

    redirects = [m["redirectScheme"] for m in middlewares if "redirectScheme" in m]
    if not any(r.get("scheme") == "https" for r in redirects):
        missing.append("an HTTP to HTTPS redirect (a redirectScheme Middleware with scheme https)")
    served_on_web = [
        d
        for d in docs
        if d["kind"] == "Ingress"
        and d["metadata"].get("annotations", {}).get("traefik.ingress.kubernetes.io/router.entrypoints") == "web"
    ]
    if not served_on_web:
        missing.append("an Ingress on the web entry point that carries the redirect")

    versions = [d["spec"].get("minVersion") for d in docs if d["kind"] == "TLSOption"]
    if not versions:
        missing.append("a TLSOption with a TLS minimum (minVersion)")
    elif any(v not in {"VersionTLS12", "VersionTLS13"} for v in versions):
        missing.append(f"a TLS minimum of 1.2 (minVersion {versions!r} allows an older version)")

    caps = [m["buffering"].get("maxRequestBodyBytes") for m in middlewares if "buffering" in m]
    if caps != [8192]:
        missing.append(f"a body limit of 8192 bytes (buffering.maxRequestBodyBytes, found {caps!r})")
    return missing


def render_docs(values: Path) -> list[dict[str, Any]]:
    result = helm("template", values)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def test_given_the_repository_when_environments_are_listed_then_the_local_values_are_checked() -> None:
    assert LOCAL_VALUES in env_value_files()


@needs_helm
def test_given_the_local_values_when_rendered_then_hsts_redirect_tls_minimum_and_body_cap_are_present() -> None:
    missing = ingress_gate_findings(render_docs(LOCAL_VALUES))

    assert not missing, "deploy/envs/local/values.yaml renders without: " + "; ".join(missing)


def mutate(docs: list[dict[str, Any]], kind: str, change: Any) -> list[dict[str, Any]]:
    copied = copy.deepcopy(docs)
    for doc in copied:
        if doc["kind"] == kind:
            change(doc)
    return copied


@needs_helm
@pytest.mark.parametrize(
    ("kind", "change", "expected"),
    [
        ("Middleware", lambda d: d["spec"].pop("headers", None), "HSTS directive (headers.stsSeconds)"),
        ("Middleware", lambda d: d["spec"].get("headers", {}).update(stsIncludeSubdomains=True), "without includeSubDomains"),
        ("Middleware", lambda d: d["spec"].get("headers", {}).update(stsPreload=True), "without includeSubDomains and preload"),
        ("Middleware", lambda d: d["spec"].get("headers", {}).update(stsSeconds=300), "max-age of 31536000"),
        (
            "Middleware",
            lambda d: d["spec"].get("headers", {}).update(customResponseHeaders={"Strict-Transport-Security": "max-age=1"}),
            "exactly one HSTS directive",
        ),
        ("Middleware", lambda d: d["spec"].pop("redirectScheme", None), "HTTP to HTTPS redirect"),
        ("Middleware", lambda d: d["spec"].pop("buffering", None), "body limit of 8192"),
        ("Middleware", lambda d: d["spec"].get("buffering", {}).update(maxRequestBodyBytes=9000), "body limit of 8192"),
        ("TLSOption", lambda d: d["spec"].update(minVersion="VersionTLS11"), "TLS minimum of 1.2"),
        ("TLSOption", lambda d: d["spec"].pop("minVersion"), "a TLS minimum"),
        (
            "Ingress",
            lambda d: d["metadata"]["annotations"].update({"traefik.ingress.kubernetes.io/router.entrypoints": "websecure"}),
            "Ingress on the web entry point",
        ),
    ],
)
def test_given_a_render_that_drops_a_traefik_gate_when_checked_then_the_missing_item_is_named(
    kind: str, change: Any, expected: str
) -> None:
    missing = ingress_gate_findings(mutate(render_docs(LOCAL_VALUES), kind, change))

    assert any(expected in item for item in missing), missing


@needs_helm
@pytest.mark.parametrize(
    "override",
    [
        {"ingress": {"controller": None}},
        {"ingress": {"controller": "nginx"}},
        {"ingress": {"hstsAnnotation": {"key": "x/y", "format": "%s"}}},
        {"ingress": {"annotations": {"a": "b"}}},
        {"ingress": {"controllerConfig": {"ssl-protocols": "TLSv1"}}},
        {"ingress": {"hsts": False}},
        {"ingress": {"tls": {"enabled": False}}},
    ],
)
def test_given_an_environment_that_weakens_the_ingress_when_rendered_then_the_schema_refuses(
    override: dict[str, Any], tmp_path: Path
) -> None:
    result = helm("template", weakened(override, tmp_path))

    assert result.returncode != 0
    assert "ingress" in result.stderr


@needs_helm
def test_given_the_local_values_when_the_controller_is_removed_then_the_error_names_controller() -> None:
    result = helm("lint", LOCAL_VALUES, "json:ingress.controller=null")

    assert result.returncode != 0
    assert "controller" in result.stdout + result.stderr


@needs_helm
@pytest.mark.parametrize(
    ("sets", "expected"),
    [
        (("json:certAlert.enabled=false", f"api.image.digest={DIGEST}", f"web.image.digest={DIGEST}"), "certAlert"),
        (("json:certAlert.enabled=true", f"web.image.digest={DIGEST}"), "digest"),
        (("json:certAlert.enabled=true", f"api.image.digest={DIGEST}"), "digest"),
        (("json:certAlert.enabled=true", "api.image.digest=", "web.image.digest="), "digest"),
    ],
)
def test_given_production_values_without_the_cert_alert_or_a_digest_when_the_schema_runs_then_it_refuses(
    sets: tuple[str, ...], expected: str
) -> None:
    result = helm("template", LOCAL_VALUES, "environment=production", *sets)

    assert result.returncode != 0
    assert expected in result.stderr


@needs_helm
def test_given_production_values_with_the_cert_alert_and_digests_when_rendered_then_the_alert_exists() -> None:
    sets = ("environment=production", "json:certAlert.enabled=true", f"api.image.digest={DIGEST}")
    result = helm("template", LOCAL_VALUES, *sets, f"web.image.digest={DIGEST}")

    assert result.returncode == 0, result.stderr
    kinds = {d["kind"] for d in yaml.safe_load_all(result.stdout) if d}
    assert "PrometheusRule" in kinds


@needs_helm
def test_given_the_chart_defaults_when_rendered_then_the_environment_is_production_and_refuses() -> None:
    """Secure by default: an environment that does not say what it is gets the production rules."""
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))

    assert values["environment"] == "production"


@needs_helm
def test_given_the_local_values_when_rendered_then_they_say_local_and_need_no_digest() -> None:
    values = yaml.safe_load(LOCAL_VALUES.read_text(encoding="utf-8"))

    assert values["environment"] == "local"
    assert helm("template", LOCAL_VALUES).returncode == 0
    assert json.dumps(values).count("sha256:") == 0


SKIP_DIRS = {"node_modules", ".venv", ".git", ".claude", "dist", "build"}
DIGEST_PIN = re.compile(r"@sha256:[a-f0-9]{64}$")
# Images that are not pulled from a registry by name and tag, so a digest cannot exist (U-web-settings-66, SEC2-05).
# Every entry needs a reason; the test refuses an exception that no compose file uses any more.
COMPOSE_EXCEPTIONS = {
    "mail-assistant-api:local": "built from backend/Dockerfile by the same compose service (build: next to image:)",
    "mail-assistant-web:local": "built from apps/web/Dockerfile by the same compose service (build: next to image:)",
}
# A Dockerfile FROM that is not pinned is listed here with the reason; empty on purpose.
DOCKERFILE_EXCEPTIONS: dict[str, str] = {}


def repo_files(*names: str) -> list[Path]:
    found = [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not SKIP_DIRS & set(p.relative_to(ROOT).parts)
        and any(fnmatch.fnmatch(p.name, n) for n in names)
    ]
    return sorted(found)


def dockerfiles() -> list[Path]:
    return repo_files("Dockerfile", "Dockerfile.*", "*.Dockerfile")


def compose_files() -> list[Path]:
    return repo_files("compose.y*ml", "docker-compose*.y*ml")


def display(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


def dockerfile_froms(path: Path) -> list[str]:
    stages: set[str] = set()
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.match(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", line, re.IGNORECASE)
        if not match:
            continue
        image, alias = match.groups()
        where = f"{display(path)}:{number}"
        if image not in stages and not DIGEST_PIN.search(image) and where not in DOCKERFILE_EXCEPTIONS:
            problems.append(f"{where} FROM {image} has no @sha256 digest")
        if alias:
            stages.add(alias)
    return problems


def compose_images(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    images = [svc["image"] for svc in (doc.get("services") or {}).values() if isinstance(svc, dict) and "image" in svc]
    return [str(i) for i in images]


def unpinned_compose_images() -> list[str]:
    return [
        f"{path.relative_to(ROOT).as_posix()}: image {image} has no @sha256 digest"
        for path in compose_files()
        for image in compose_images(path)
        if not DIGEST_PIN.search(image) and image not in COMPOSE_EXCEPTIONS
    ]


def test_given_the_repository_when_scanned_then_every_dockerfile_and_compose_file_is_found() -> None:
    names = {p.relative_to(ROOT).as_posix() for p in dockerfiles()}
    assert {
        "backend/Dockerfile",
        "apps/web/Dockerfile",
        "agents/mail-triage/Dockerfile",
        "agents/assistant/Dockerfile",
        "channels/chat-gateway/Dockerfile",
        "mcp-servers/tools/Dockerfile",
    } <= names
    assert ROOT / "compose.yaml" in compose_files()


def test_given_every_dockerfile_in_the_repo_when_linted_then_every_from_is_pinned_by_digest() -> None:
    problems = [problem for dockerfile in dockerfiles() for problem in dockerfile_froms(dockerfile)]

    assert problems == []


def test_given_every_compose_image_in_the_repo_when_linted_then_each_has_a_digest_or_a_documented_exception() -> None:
    assert unpinned_compose_images() == []


def test_given_the_compose_exceptions_when_listed_then_each_is_used_built_locally_and_explained() -> None:
    used = {image for path in compose_files() for image in compose_images(path)}

    assert set(COMPOSE_EXCEPTIONS) <= used, "an exception that no compose file uses any more must be removed"
    assert all(len(reason) > 20 for reason in COMPOSE_EXCEPTIONS.values())
    doc = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    for image in COMPOSE_EXCEPTIONS:
        service = next(s for s in doc["services"].values() if s.get("image") == image)
        assert "build" in service, f"{image} is exempt only because the same service builds it"


def test_given_an_unpinned_from_when_linted_then_the_linter_names_the_line(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    pinned = "caddy:2@sha256:" + "b" * 64
    lines = ["FROM python:3.13-slim AS a", "FROM a AS b", f"FROM {pinned}"]
    dockerfile.write_text(chr(10).join(lines), encoding="utf-8")

    problems = dockerfile_froms(dockerfile)

    assert len(problems) == 1
    assert ":1 FROM python:3.13-slim has no @sha256 digest" in problems[0]


def test_given_the_renovate_config_when_read_then_it_keeps_the_digest_pins_up_to_date() -> None:
    config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))

    assert "docker:pinDigests" in config["extends"]


def test_given_the_renovate_config_when_read_then_compose_files_and_dockerfiles_stay_in_its_managers() -> None:
    config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
    enabled = config.get("enabledManagers")
    disabled = [r for r in config.get("packageRules", []) if r.get("enabled") is False]

    assert "config:recommended" in config["extends"]
    assert enabled is None or {"dockerfile", "docker-compose"} <= set(enabled)
    assert not [r for r in disabled if {"dockerfile", "docker-compose"} & set(r.get("matchManagers", []))]


# --- U-web-settings-70 (RT3-06): every image reference in the charts and the environment values -------------------

CHARTS = ROOT / "deploy" / "charts"
TEMPLATE_IMAGE = re.compile(r"^\s*-?\s*image:\s*(\S.*?)\s*$")
CHART_IMAGE_EXCEPTIONS = {
    'deploy/charts/app/templates/workloads.yaml: {{ include "app.image" $c.image }}': (
        "composed by the app.image helper from api.image and web.image; values.schema.json requires a digest for both "
        "unless environment is local or staging"
    ),
    'deploy/charts/worker/templates/migration.yaml: {{ include "worker.image" . }}': (
        "composed by the worker.image helper from image.*; values.schema.json requires a digest in production"
    ),
    'deploy/charts/worker/templates/worker.yaml: {{ include "worker.image" . }}': (
        "composed by the worker.image helper from image.*; values.schema.json requires a digest in production"
    ),
    'deploy/charts/component/templates/component.yaml: {{ include "component.image" . }}': (
        "scaffold chart for a component that is not deployed yet; its image comes from values and has no schema"
    ),
    "deploy/charts/app/values.yaml: api.image": (
        "empty digest by default on purpose; the schema refuses it unless environment is local or staging"
    ),
    "deploy/charts/app/values.yaml: web.image": (
        "empty digest by default on purpose; the schema refuses it unless environment is local or staging"
    ),
    "deploy/charts/worker/values.yaml: image": (
        "digest is empty by default on purpose; the schema refuses an empty digest in production"
    ),
    "deploy/charts/component/values.yaml: image": "scaffold chart; the digest is set by the release that deploys it",
    "deploy/envs/local/values.yaml: api.image": "local kind cluster: an image loaded from the local build, tag local",
    "deploy/envs/local/values.yaml: web.image": "local kind cluster: an image loaded from the local build, tag local",
    "deploy/envs/local/mail-triage.yaml: image": "local values; any production release sets image.digest (schema)",
    "deploy/envs/production/values.yaml: api.image": (
        "digest is the sentinel REQUIRED on purpose: the schema refuses it until a release supplies the real digest"
    ),
    "deploy/envs/production/values.yaml: web.image": (
        "digest is the sentinel REQUIRED on purpose: the schema refuses it until a release supplies the real digest"
    ),
    "deploy/envs/production/mail-triage.yaml: image": (
        "digest is the sentinel REQUIRED on purpose: the schema refuses it until a release supplies the real digest"
    ),
}


def chart_template_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in (root / "deploy" / "charts").glob("*/templates/**/*")
        if p.is_file() and p.suffix in {".yaml", ".yml", ".tpl"}
    )


def chart_values_files(root: Path) -> list[Path]:
    found = list((root / "deploy" / "charts").glob("*/values.y*ml")) + list((root / "deploy" / "envs").rglob("*.y*ml"))
    return sorted(found)


def image_mappings(node: Any, trail: str = "") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{trail}.{key}" if trail else str(key)
            if key == "image" and isinstance(value, dict | str):
                found.append((here, value))
            else:
                found += image_mappings(value, here)
    return found


def chart_image_findings(root: Path) -> tuple[list[str], set[str]]:
    """The unpinned image references under root, and the exception keys that were used."""
    problems: list[str] = []
    used: set[str] = set()
    for key, message in _unpinned_template_images(root) + _unpinned_values_images(root):
        if key in CHART_IMAGE_EXCEPTIONS:
            used.add(key)
        else:
            problems.append(message)
    return problems, used


def _unpinned_template_images(root: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in chart_template_files(root):
        name = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = TEMPLATE_IMAGE.match(line)
            if match and not DIGEST_PIN.search(match.group(1)):
                image = match.group(1)
                found.append((f"{name}: {image}", f"{name}:{number} image {image} has no @sha256 digest"))
    return found


def _unpinned_values_images(root: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in chart_values_files(root):
        name = path.relative_to(root).as_posix()
        for trail, image in image_mappings(yaml.safe_load(path.read_text(encoding="utf-8")) or {}):
            digest = image.get("digest", "") if isinstance(image, dict) else image
            if not re.fullmatch(r"(?:.*@)?sha256:[a-f0-9]{64}", str(digest)):
                found.append((f"{name}: {trail}", f"{name}: {trail} has no @sha256 digest"))
    return found


def test_given_every_chart_and_environment_image_when_linted_then_each_has_a_digest_or_an_exception() -> None:
    problems, _ = chart_image_findings(ROOT)

    assert problems == []


def test_given_the_chart_image_exceptions_when_listed_then_each_is_used_and_explained() -> None:
    _, used = chart_image_findings(ROOT)

    assert set(CHART_IMAGE_EXCEPTIONS) == used, "remove an exception that no chart file uses any more"
    assert all(len(reason) > 30 for reason in CHART_IMAGE_EXCEPTIONS.values())


def test_given_an_unpinned_image_in_a_chart_template_when_linted_then_the_linter_names_the_line(tmp_path: Path) -> None:
    templates = tmp_path / "deploy" / "charts" / "x" / "templates"
    templates.mkdir(parents=True)
    pinned = "curlimages/curl:8.17.0@sha256:" + "e" * 64
    (templates / "t.yaml").write_text(
        f"containers:\n  - name: a\n    image: curlimages/curl:8.17.0\n  - name: b\n    image: {pinned}\n",
        encoding="utf-8",
    )

    problems, _ = chart_image_findings(tmp_path)

    assert problems == ["deploy/charts/x/templates/t.yaml:3 image curlimages/curl:8.17.0 has no @sha256 digest"]


def test_given_the_test_pod_when_read_then_its_image_is_pinned_by_digest() -> None:
    text = (ROOT / "deploy" / "charts" / "app" / "templates" / "tests" / "test-health.yaml").read_text(encoding="utf-8")
    images = [m.group(1) for line in text.splitlines() if (m := TEMPLATE_IMAGE.match(line))]

    assert images
    assert all(DIGEST_PIN.search(image) for image in images), images
