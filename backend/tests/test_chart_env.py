"""U-web-settings-52: the chart sets the trusted proxies of the api (ADR-0039; RT-02, SEC-01; W-7, W-17).

The api Deployment is rendered with the real ``helm template`` and its env is read back; the CIDR list uses the same
JSON format that ``Settings`` parses.
"""

import ipaddress
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "charts" / "app"
LOCAL_VALUES = ROOT / "deploy" / "envs" / "local" / "values.yaml"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")


def helm(command: str, *sets: str) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    base = [HELM, command, "app", str(CHART)] if command == "template" else [HELM, command, str(CHART)]
    base += ["-f", str(LOCAL_VALUES)]
    for item in sets:
        base += ["--set-json" if item.startswith("json:") else "--set", item.removeprefix("json:")]
    return subprocess.run(base, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def api_env(*sets: str) -> dict[str, str]:
    result = helm("template", *sets)
    assert result.returncode == 0, result.stderr
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    api = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "app-api")
    env = api["spec"]["template"]["spec"]["containers"][0]["env"]
    return {item["name"]: item["value"] for item in env if "value" in item}


@needs_helm
def test_given_the_local_values_when_the_api_env_is_read_then_the_proxy_settings_are_valid() -> None:
    env = api_env()

    cidrs: list[str] = json.loads(env["APP_TRUSTED_PROXY_CIDRS"])
    assert cidrs != []
    for cidr in cidrs:
        ipaddress.ip_network(cidr, strict=False)
    assert int(env["APP_TRUSTED_PROXY_HOPS"]) >= 1


@needs_helm
def test_given_the_rendered_proxy_env_when_parsed_by_settings_then_the_values_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = api_env()
    monkeypatch.setenv("APP_TRUSTED_PROXY_CIDRS", env["APP_TRUSTED_PROXY_CIDRS"])
    monkeypatch.setenv("APP_TRUSTED_PROXY_HOPS", env["APP_TRUSTED_PROXY_HOPS"])

    settings = Settings()

    assert settings.trusted_proxy_cidrs == json.loads(env["APP_TRUSTED_PROXY_CIDRS"])
    assert settings.trusted_proxy_hops == int(env["APP_TRUSTED_PROXY_HOPS"])


@needs_helm
def test_given_hops_set_in_values_when_rendered_then_the_env_carries_them() -> None:
    env = api_env("api.config.trustedProxyHops=2", 'json:api.config.trustedProxyCidrs=["10.1.0.0/16","fd00::/8"]')

    assert env["APP_TRUSTED_PROXY_HOPS"] == "2"
    assert json.loads(env["APP_TRUSTED_PROXY_CIDRS"]) == ["10.1.0.0/16", "fd00::/8"]


@needs_helm
@pytest.mark.parametrize(
    "sets",
    [
        ("json:api.config.trustedProxyCidrs=[]",),
        ("json:api.config.trustedProxyCidrs=null",),
        ('json:api.config.trustedProxyCidrs=["not-a-cidr"]',),
        ("api.config.trustedProxyHops=0",),
    ],
)
def test_given_ingress_enabled_and_no_valid_proxy_setting_when_rendered_then_the_schema_refuses(
    sets: tuple[str, ...],
) -> None:
    result = helm("template", "ingress.enabled=true", *sets)

    assert result.returncode != 0
    assert "trustedProxy" in result.stderr


@needs_helm
def test_given_ingress_disabled_when_the_list_is_empty_then_the_chart_renders() -> None:
    result = helm("template", "ingress.enabled=false", "json:api.config.trustedProxyCidrs=[]")

    assert result.returncode == 0, result.stderr
