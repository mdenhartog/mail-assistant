"""U-web-settings-57: ingress gates for HSTS, the certificate alert and image digests (ADR-0037, ADR-0039).

Findings RT-10, SEC-05, SEC-07; AC-18, W-9. The ingress controller is still an open point (D-7), so the gates read what
the rendered Ingress annotations and the declared controller config say, not which controller consumes them.
"""

from __future__ import annotations

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
REDIRECT_KEYS = ("ssl-redirect", "force-ssl-redirect")
ALLOWED_TLS = {"TLSv1.2", "TLSv1.3", "VersionTLS12", "VersionTLS13", "tls1.2", "tls1.3", "1.2", "1.3"}


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


def tls_findings(config: dict[str, str]) -> list[str]:
    versions = [
        (k, v)
        for k, v in config.items()
        if re.search(r"ssl-protocols|tls-?(min|version)|min-?version", k, re.IGNORECASE)
    ]
    if not versions:
        return ["a TLS minimum (a controllerConfig key such as ssl-protocols or minVersion)"]
    return [
        f"a TLS minimum of 1.2 ({key}={value!r} allows an older version)"
        for key, value in versions
        if not set(re.split(r"[\s,]+", value.strip())) <= ALLOWED_TLS
    ]


def weakened(override: dict[str, Any], tmp: Path) -> Path:
    """Write a copy of the local values with `override` merged in (null deletes a key)."""
    merged = deep_merge(yaml.safe_load(LOCAL_VALUES.read_text(encoding="utf-8")), override)
    path = tmp / "values.yaml"
    path.write_text(yaml.safe_dump(merged), encoding="utf-8")
    return path


def missing_gates(values: Path) -> list[str]:
    """Return what an environment is missing: the HSTS directive, the HTTP redirect and the TLS minimum."""
    result = helm("template", values)
    if result.returncode != 0:
        return [f"a chart that renders ({result.stderr.strip()})"]
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    ingress = next((d for d in docs if d["kind"] == "Ingress"), None)
    if ingress is None:
        return ["an Ingress"]
    annotations: dict[str, str] = ingress["metadata"]["annotations"]
    merged = deep_merge(
        yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8")),
        yaml.safe_load(values.read_text(encoding="utf-8")),
    )
    config: dict[str, str] = merged["ingress"].get("controllerConfig", {})
    missing: list[str] = []

    hsts = [v for v in annotations.values() if "max-age=" in v]
    if not hsts:
        missing.append("an HSTS directive (an annotation value with max-age=)")
    elif any(re.search(r"includeSubDomains|preload", v) for v in hsts):
        missing.append("an HSTS directive without includeSubDomains and preload")

    redirects = {k: v for k, v in annotations.items() if "redirect" in k.lower() or "redirect" in v.lower()}
    if not redirects or all(v.strip().lower() in {"false", "off", "0"} for v in redirects.values()):
        missing.append("an HTTP to HTTPS redirect (an annotation naming a redirect that is not switched off)")

    missing.extend(tls_findings(config))
    return missing


def test_given_the_repository_when_environments_are_listed_then_the_local_values_are_checked() -> None:
    assert LOCAL_VALUES in env_value_files()


@needs_helm
@pytest.mark.parametrize("values", env_value_files(), ids=lambda p: p.parent.name)
def test_given_an_environment_values_file_when_rendered_then_hsts_redirect_and_tls_minimum_are_present(
    values: Path,
) -> None:
    missing = missing_gates(values)

    assert not missing, f"{values.relative_to(ROOT)} is missing: " + "; ".join(missing)


@needs_helm
@pytest.mark.parametrize(
    ("override", "expected"),
    [
        (
            {"ingress": {"annotations": {f"nginx.ingress.kubernetes.io/{k}": None for k in REDIRECT_KEYS}}},
            "redirect",
        ),
        (
            {"ingress": {"annotations": {f"nginx.ingress.kubernetes.io/{k}": "false" for k in REDIRECT_KEYS}}},
            "redirect",
        ),
        ({"ingress": {"controllerConfig": {"ssl-protocols": None}}}, "TLS minimum"),
        ({"ingress": {"controllerConfig": {"ssl-protocols": "TLSv1 TLSv1.1 TLSv1.2"}}}, "TLS minimum of 1.2"),
        ({"ingress": {"hstsAnnotation": {"format": "%s; preload"}}}, "a chart that renders"),
    ],
)
def test_given_an_environment_that_drops_a_gate_when_checked_then_the_missing_item_is_named(
    override: dict[str, Any], expected: str, tmp_path: Path
) -> None:
    missing = missing_gates(weakened(override, tmp_path))

    assert any(expected in item for item in missing), missing


@needs_helm
@pytest.mark.parametrize("key", ["", " "])
def test_given_hsts_true_and_an_empty_annotation_key_when_the_schema_runs_then_it_refuses(key: str) -> None:
    for command in ("template", "lint"):
        result = helm(command, LOCAL_VALUES, f"ingress.hstsAnnotation.key={key}")

        assert result.returncode != 0, command
        assert "hstsAnnotation" in result.stdout + result.stderr


@needs_helm
def test_given_hsts_true_and_no_annotation_object_when_the_schema_runs_then_it_refuses() -> None:
    result = helm("template", LOCAL_VALUES, "json:ingress.hstsAnnotation=null")

    assert result.returncode != 0
    assert "hstsAnnotation" in result.stderr


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
