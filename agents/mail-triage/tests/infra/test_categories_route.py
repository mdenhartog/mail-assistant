"""U-mail-categories-20: the list save has its own Traefik route, 32 KB buffering (MC-12, ADR-0034, ADR-0040)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
CHART = ROOT / "deploy" / "charts" / "app"
LOCAL_VALUES = ROOT / "deploy" / "envs" / "local" / "values.yaml"
README = CHART / "README.md"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
TRAEFIK = "traefik.ingress.kubernetes.io"


def helm(command: str, *sets: str) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    base = [HELM, command, "app", str(CHART)] if command == "template" else [HELM, command, str(CHART)]
    if command == "lint":
        base.append("--strict")
    base += ["-f", str(LOCAL_VALUES)]
    for item in sets:
        base += ["--set", item]
    return subprocess.run(base, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def render(*sets: str) -> list[dict[str, Any]]:
    result = helm("template", *sets)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def of_kind(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [doc for doc in docs if doc["kind"] == kind]


def limit_caps(docs: list[dict[str, Any]]) -> dict[str, int]:
    """Middleware name to its buffering cap."""
    return {
        d["metadata"]["name"]: d["spec"]["buffering"]["maxRequestBodyBytes"]
        for d in of_kind(docs, "Middleware")
        if "buffering" in d["spec"]
    }


def the_route(docs: list[dict[str, Any]]) -> dict[str, Any]:
    routes = of_kind(docs, "IngressRoute")
    assert len(routes) == 1, "one IngressRoute: the list save"
    assert len(routes[0]["spec"]["routes"]) == 1
    return routes[0]


@needs_helm
def test_given_the_rendered_chart_when_read_then_put_api_categories_has_its_own_route_with_a_32_kb_limit() -> None:
    docs = render()
    route = the_route(docs)
    spec = route["spec"]["routes"][0]
    host = yaml.safe_load(LOCAL_VALUES.read_text(encoding="utf-8"))["ingress"]["host"]
    caps = limit_caps(docs)

    assert spec["match"] == f"Host(`{host}`) && Method(`PUT`) && Path(`/api/categories`)"
    assert spec["services"] == [{"name": "app-api", "port": "http"}]
    assert route["spec"]["entryPoints"] == ["websecure"]
    on_route = [caps[m["name"]] for m in spec["middlewares"] if m["name"] in caps]
    assert on_route == [32768]  # exactly one limit on this route, the 32 KB one
    assert sorted(caps.values()) == [8192, 32768]


@needs_helm
def test_given_the_rendered_chart_when_read_then_every_other_path_keeps_the_8_kb_limit() -> None:
    docs = render()
    caps = {f"default-{name}@kubernetescrd": cap for name, cap in limit_caps(docs).items()}
    https = next(d for d in of_kind(docs, "Ingress") if d["spec"].get("tls"))
    refs = https["metadata"]["annotations"][f"{TRAEFIK}/router.middlewares"].split(",")
    paths = [(p["path"], p["pathType"]) for p in https["spec"]["rules"][0]["http"]["paths"]]

    assert [caps[r] for r in refs if r in caps] == [8192]
    assert paths == [("/api", "Prefix"), ("/auth", "Prefix"), ("/", "Prefix")]


@needs_helm
def test_given_the_rendered_route_when_matched_then_only_the_exact_method_and_path_can_match() -> None:
    spec = the_route(render())["spec"]["routes"][0]
    match = spec["match"]

    # POST, the trailing slash variant and any other /api path fail this rule and fall to the 8 KB Ingress.
    for forbidden in ("PathPrefix", "HostRegexp", "PathRegexp", "||", "Path(`/api/categories/`)"):
        assert forbidden not in match, forbidden
    assert "Path(`/api/categories`)" in match
    assert match.count("Method(") == 1
    assert "Method(`PUT`)" in match
    assert spec["priority"] >= 1000  # wins over the /api prefix router of the Ingress


@needs_helm
def test_given_the_rendered_route_when_read_then_it_keeps_hsts_the_tls_minimum_and_the_redirect() -> None:
    docs = render()
    spec = the_route(docs)["spec"]
    names = [m["name"] for m in spec["routes"][0]["middlewares"]]
    hsts = [d["metadata"]["name"] for d in of_kind(docs, "Middleware") if "stsSeconds" in d["spec"].get("headers", {})]
    option = of_kind(docs, "TLSOption")[0]["metadata"]["name"]
    https = next(d for d in of_kind(docs, "Ingress") if d["spec"].get("tls"))
    redirect = next(d for d in of_kind(docs, "Ingress") if not d["spec"].get("tls"))

    assert len(hsts) == 1
    assert hsts[0] in names
    assert spec["tls"] == {"secretName": https["spec"]["tls"][0]["secretName"], "options": {"name": option}}
    # plain HTTP for every path, this one included, still gets the redirect of the web entry point
    assert redirect["metadata"]["annotations"][f"{TRAEFIK}/router.entrypoints"] == "web"
    assert redirect["spec"]["rules"][0]["http"]["paths"][0]["path"] == "/"
    assert redirect["spec"]["rules"][0]["http"]["paths"][0]["pathType"] == "Prefix"
    assert any("redirectScheme" in d["spec"] for d in of_kind(docs, "Middleware"))


@needs_helm
def test_given_body_limit_values_when_rendered_then_the_limits_follow_them() -> None:
    docs = render("ingress.bodyLimitBytes=4096", "ingress.categoriesBodyLimitBytes=65536")

    assert sorted(limit_caps(docs).values()) == [4096, 65536]


@needs_helm
@pytest.mark.parametrize(
    "setting",
    [
        "ingress.bodyLimitBytes=0",
        "ingress.categoriesBodyLimitBytes=0",
        "ingress.bodyLimitBytes=-1",
        "ingress.categoriesBodyLimitBytes=-5",
        "ingress.categoriesBodyLimitBytes=big",
    ],
)
def test_given_a_body_cap_below_one_when_linted_then_the_schema_rejects_it(setting: str) -> None:
    result = helm("lint", setting)

    assert result.returncode != 0, setting
    assert setting.split("=", maxsplit=1)[0].split(".")[1] in result.stdout + result.stderr


@needs_helm
def test_given_the_ingress_is_off_when_rendered_then_no_ingress_route_exists() -> None:
    assert not of_kind(render("ingress.enabled=false"), "IngressRoute")


@needs_helm
def test_given_the_local_values_when_linted_then_the_chart_has_no_findings() -> None:
    result = helm("lint")

    assert result.returncode == 0, result.stdout + result.stderr


def test_given_the_readme_when_read_then_it_names_both_body_limits_and_the_reason() -> None:
    sections = README.read_text(encoding="utf-8").split("## Request body limits", 1)
    assert len(sections) == 2, "a section 'Request body limits'"
    body = sections[1].split("\n## ", 1)[0]

    for needle in (
        "8192",
        "32768",
        "PUT /api/categories",
        "MC-12",
        "ADR-0034",
        "ingress.bodyLimitBytes",
        "ingress.categoriesBodyLimitBytes",
        "27 KB",  # the reason: a full list is about 27 KB and does not fit in 8 KB
    ):
        assert needle in body, needle


def test_given_the_readme_when_read_then_the_refused_api_env_keys_name_the_two_body_limits_and_why() -> None:
    lines = README.read_text(encoding="utf-8").splitlines()
    line = next(item for item in lines if item.startswith("- `api.env` and `web.env` refuse"))

    for needle in ("`APP_CATEGORIES_MAILBOX_ID`", "`APP_ROUTE_BODY_LIMITS`", "`APP_BODY_LIMIT_BYTES`", "8192", "32768"):
        assert needle in line, needle
    assert "ingress" in line.lower()
