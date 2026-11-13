"""U-web-settings-57: ingress gates for HSTS, the certificate alert and image digests (ADR-0037, ADR-0039).

Findings RT-10, SEC-05, SEC-07; AC-18, W-9. The ingress controller is still an open point (D-7), so the gates read what
the rendered Ingress annotations and the declared controller config say, not which controller consumes them.
"""

from __future__ import annotations

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


def dockerfile_froms(path: Path) -> list[str]:
    stages: set[str] = set()
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.match(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", line, re.IGNORECASE)
        if not match:
            continue
        image, alias = match.groups()
        if image not in stages and not re.search(r"@sha256:[a-f0-9]{64}$", image):
            problems.append(f"{path.relative_to(ROOT)}:{number} FROM {image} has no @sha256 digest")
        if alias:
            stages.add(alias)
    return problems


@pytest.mark.parametrize("dockerfile", [ROOT / "backend" / "Dockerfile", ROOT / "apps" / "web" / "Dockerfile"])
def test_given_a_dockerfile_when_linted_then_every_from_is_pinned_by_digest(dockerfile: Path) -> None:
    assert dockerfile_froms(dockerfile) == []


def test_given_the_renovate_config_when_read_then_it_keeps_the_digest_pins_up_to_date() -> None:
    config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))

    assert "docker:pinDigests" in config["extends"]
