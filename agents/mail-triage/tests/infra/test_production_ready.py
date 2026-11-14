"""U-web-settings-74: production is prepared and not deployed (ADR-0040, ADR-0012, ADR-0029, ADR-0037).

The production values name every value Marco must supply with the sentinel `REQUIRED` and a `# REQUIRED` comment. A
render without them fails, naming the value; with them (the fixtures below, never real data) the chart passes the gates
of U-57, U-66 and U-70 and renders the Traefik objects. Nothing here talks to a cluster: `helm template` and `helm lint`
render files only, and no workflow applies the Argo CD manifest or the production values.
"""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
APP_CHART = ROOT / "deploy" / "charts" / "app"
WORKER_CHART = ROOT / "deploy" / "charts" / "worker"
PROD_APP = ROOT / "deploy" / "envs" / "production" / "values.yaml"
PROD_WORKER = ROOT / "deploy" / "envs" / "production" / "mail-triage.yaml"
ARGO = ROOT / "deploy" / "argocd" / "application.yaml"
WORKFLOWS = ROOT / ".github" / "workflows"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
SENTINEL = "REQUIRED"
DIGEST_API = "sha256:" + "1" * 64  # well formed, not an image anybody runs
DIGEST_WEB = "sha256:" + "2" * 64
DIGEST_AGENT = "sha256:" + "3" * 64

# What Marco supplies for the app chart: a fixture per REQUIRED path (invented, never a real host, address or name).
APP_SUPPLY: dict[str, Any] = {
    "api.image.digest": DIGEST_API,
    "web.image.digest": DIGEST_WEB,
    "api.config.username": "fixture-user",
    "api.config.emailAddress": "fixture-user@home.arpa",
    "api.config.publicOrigin": "https://fixture.home.arpa",
    "api.config.smtp.host": "smtp.fixture.home.arpa",
    "api.config.smtp.port": 587,
    "api.config.smtp.from": "mail-assistant@fixture.home.arpa",
    "api.config.trustedProxyCidrs.0": "10.42.0.0/16",
    "ingress.host": "fixture.home.arpa",
    "ingress.clusterIssuer": "fixture-private-ca",
    "networkPolicy.egress.database.cidr": "10.0.0.10/32",
    "networkPolicy.egress.smtp.cidr": "10.0.0.11/32",
}
WORKER_SUPPLY: dict[str, Any] = {
    "image.digest": DIGEST_AGENT,
    "envFromSecret": "fixture-agent-secrets",
    "database.tls.caConfigMap": "fixture-db-ca",
    "migration.secretName": "fixture-migration",
}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    assert HELM is not None
    return subprocess.run([HELM, *args], capture_output=True, text=True, timeout=60, check=False)  # noqa: S603


def load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def required_paths(node: Any, trail: str = "") -> list[str]:
    """Every scalar in the document that is the sentinel, as a dotted path (list items by index)."""
    found: list[str] = []
    items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else []
    for key, value in items:
        here = f"{trail}.{key}" if trail else str(key)
        if value == SENTINEL:
            found.append(here)
        else:
            found += required_paths(value, here)
    return found


def set_path(doc: dict[str, Any], path: str, value: Any) -> None:
    node: Any = doc
    parts = path.split(".")
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(parts[-1])] = value
    else:
        node[parts[-1]] = value


def values_file(tmp: Path, source: Path, supply: dict[str, Any], *, leave: str | None = None) -> Path:
    """The production values with every REQUIRED value supplied, except `leave`, which keeps the sentinel."""
    doc = copy.deepcopy(load(source))
    for path, value in supply.items():
        if path != leave:
            set_path(doc, path, value)
    out = tmp / f"{source.stem}-supplied.yaml"
    out.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return out


def render(chart: Path, release: str, values: Path, *sets: str) -> subprocess.CompletedProcess[str]:
    args = ["template", release, str(chart), "-f", str(values)]
    for item in sets:
        args += ["--set-json" if item.startswith("json:") else "--set", item.removeprefix("json:")]
    return run(*args)


def names(path: str, output: str) -> bool:
    """The output names the value: Helm's schema errors use `/api/config/x`, the chart's own errors `api.config.x`."""
    return path in output or "/" + path.replace(".", "/") in output


def docs_of(result: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def of_kind(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [doc for doc in docs if doc["kind"] == kind]


@pytest.fixture
def supplied_app(tmp_path: Path) -> Path:
    return values_file(tmp_path, PROD_APP, APP_SUPPLY)


@pytest.fixture
def supplied_worker(tmp_path: Path) -> Path:
    return values_file(tmp_path, PROD_WORKER, WORKER_SUPPLY)


# --- Criterion 2 (inputs): every REQUIRED value is marked, named and covered by a fixture ---------------------------


def test_given_the_production_files_when_read_then_they_exist_and_say_production() -> None:
    assert load(PROD_APP)["environment"] == "production"
    assert load(PROD_WORKER)["environment"] == "production"


@pytest.mark.parametrize(
    ("path", "supply"), [(PROD_APP, APP_SUPPLY), (PROD_WORKER, WORKER_SUPPLY)], ids=["app", "worker"]
)
def test_given_the_production_values_when_read_then_every_required_value_has_a_fixture(
    path: Path, supply: dict[str, Any]
) -> None:
    assert sorted(required_paths(load(path))) == sorted(supply)


@pytest.mark.parametrize("path", [PROD_APP, PROD_WORKER, ARGO], ids=lambda p: p.name)
def test_given_a_required_value_when_read_then_its_line_carries_a_required_comment_with_a_name(path: Path) -> None:
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines() if re.search(r":\s*\"?REQUIRED\"?\s*(#|$)", line)
    ]
    assert lines, path.name
    for line in lines:
        assert re.search(r"#\s*REQUIRED\b\s*[:(-]?\s*\S{3,}", line), line


@pytest.mark.parametrize("path", [PROD_APP, PROD_WORKER], ids=lambda p: p.name)
def test_given_the_production_files_when_read_then_no_secret_or_fake_digest_is_in_them(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    assert not re.search(r"sha256:[a-f0-9]{64}", text), "a digest in the file must come from a release, not from here"
    assert not re.search(r"postgres(ql)?(\+\w+)?://\S+:\S+@", text)
    assert not re.search(r"(password|hashKey|csrfKey|databaseUrl|smtpUser|token)\s*:\s*\S", text, re.IGNORECASE)


# --- Criterion 2: a render without any one REQUIRED value fails and names it ----------------------------------------


@needs_helm
def test_given_the_production_values_as_they_are_when_rendered_then_the_chart_refuses() -> None:
    app = render(APP_CHART, "app", PROD_APP)
    worker = render(WORKER_CHART, "mail-triage", PROD_WORKER)

    assert app.returncode != 0
    assert worker.returncode != 0


@needs_helm
@pytest.mark.parametrize("missing", sorted(APP_SUPPLY))
def test_given_the_app_values_when_one_required_value_is_missing_then_the_render_fails_naming_it(
    missing: str, tmp_path: Path
) -> None:
    values = values_file(tmp_path, PROD_APP, APP_SUPPLY, leave=missing)

    result = render(APP_CHART, "app", values)

    assert result.returncode != 0, missing
    assert names(missing, result.stderr), result.stderr


@needs_helm
@pytest.mark.parametrize("missing", sorted(WORKER_SUPPLY))
def test_given_the_worker_values_when_one_required_value_is_missing_then_the_render_fails_naming_it(
    missing: str, tmp_path: Path
) -> None:
    values = values_file(tmp_path, PROD_WORKER, WORKER_SUPPLY, leave=missing)

    result = render(WORKER_CHART, "mail-triage", values)

    assert result.returncode != 0, missing
    assert names(missing, result.stderr), result.stderr


@needs_helm
def test_given_the_app_values_when_lint_runs_without_the_required_values_then_it_fails(tmp_path: Path) -> None:
    result = run("lint", str(APP_CHART), "--strict", "-f", str(PROD_APP))

    assert result.returncode != 0


# --- Criterion 1: with every REQUIRED value the gates of U-57, U-66 and U-70 pass -----------------------------------


@needs_helm
def test_given_the_required_values_when_linted_and_rendered_then_the_chart_passes(
    supplied_app: Path, supplied_worker: Path
) -> None:
    assert run("lint", str(APP_CHART), "--strict", "-f", str(supplied_app)).returncode == 0
    assert run("lint", str(WORKER_CHART), "--strict", "-f", str(supplied_worker)).returncode == 0
    assert docs_of(render(APP_CHART, "app", supplied_app))
    assert docs_of(render(WORKER_CHART, "mail-triage", supplied_worker))


@needs_helm
def test_given_the_rendered_production_app_when_read_then_digests_cert_alert_and_proxies_are_set(
    supplied_app: Path,
) -> None:
    docs = docs_of(render(APP_CHART, "app", supplied_app))
    deployments = {d["metadata"]["name"]: d for d in of_kind(docs, "Deployment")}
    images = {n: d["spec"]["template"]["spec"]["containers"][0]["image"] for n, d in deployments.items()}
    api_env = {
        e["name"]: e.get("value") for e in deployments["app-api"]["spec"]["template"]["spec"]["containers"][0]["env"]
    }

    assert images["app-api"].endswith(f"@{DIGEST_API}")
    assert images["app-web"].endswith(f"@{DIGEST_WEB}")
    assert api_env["APP_ENVIRONMENT"] == "production"
    assert api_env["APP_TRUSTED_PROXY_CIDRS"] == '["10.42.0.0/16"]'
    assert api_env["APP_PUBLIC_ORIGIN"] == "https://fixture.home.arpa"
    rule = next(d for d in of_kind(docs, "PrometheusRule") if "cert-expiry" in d["metadata"]["name"])
    assert "AppCertificateExpiresSoon" in str(rule)
    assert deployments["app-api"]["spec"]["replicas"] == 1


@needs_helm
def test_given_the_rendered_production_app_when_read_then_the_policy_peer_is_the_traefik_pods(
    supplied_app: Path,
) -> None:
    docs = docs_of(render(APP_CHART, "app", supplied_app))
    policy = next(d for d in of_kind(docs, "NetworkPolicy") if d["metadata"]["name"] == "app-allow-ingress")
    peers = [peer for rule in policy["spec"]["ingress"] for peer in rule["from"]]

    assert peers == [
        {
            "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "traefik"}},
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": "traefik"}},
        }
    ]


@needs_helm
@pytest.mark.parametrize(
    "setting",
    [
        "api.env.APP_ENVIRONMENT=development",
        "api.env.app_trusted_proxy_cidrs=[]",
        "api.env.APP_RATE_LIMIT_PER_MINUTE=100000",
        "web.env.APP_BODY_LIMIT_BYTES=10000000",
    ],
)
def test_given_the_production_values_when_a_forbidden_key_is_added_then_the_render_fails(
    setting: str, supplied_app: Path
) -> None:
    result = render(APP_CHART, "app", supplied_app, setting)

    assert result.returncode != 0
    assert setting.split("=", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1] in result.stderr


@needs_helm
@pytest.mark.parametrize(
    "sets",
    [
        ("json:certAlert.enabled=false",),
        ("api.image.digest=",),
        ("environment=staging", "ingress.controller=nginx"),
        ("json:api.config.trustedProxyCidrs=[]",),
    ],
)
def test_given_the_production_values_when_a_gate_is_weakened_then_the_render_fails(
    sets: tuple[str, ...], supplied_app: Path
) -> None:
    assert render(APP_CHART, "app", supplied_app, *sets).returncode != 0


def test_given_the_production_values_when_read_then_they_hold_no_override_of_the_chart_owned_settings() -> None:
    values = load(PROD_APP)

    assert not values.get("api", {}).get("env")
    assert not values.get("web", {}).get("env")
    assert values["certAlert"]["enabled"] is True
    assert values["ingress"]["controller"] == "traefik"
    assert values["ingress"]["localDomainSuffix"] == "home.arpa"  # local only (ADR-0037)
    assert values["ingress"]["tls"] == {"enabled": True}
    assert values["ingress"]["hsts"] is True


@needs_helm
def test_given_the_production_worker_values_when_rendered_then_it_is_production_with_verify_full_and_a_digest(
    supplied_worker: Path,
) -> None:
    docs = docs_of(render(WORKER_CHART, "mail-triage", supplied_worker))
    env: dict[str, str] = {}
    for kind in ("Deployment", "Job"):
        for doc in of_kind(docs, kind):
            for container in doc["spec"]["template"]["spec"]["containers"]:
                env |= {e["name"]: e.get("value", "") for e in container.get("env", [])}
    images = [
        c["image"]
        for kind in ("Deployment", "Job")
        for d in of_kind(docs, kind)
        for c in d["spec"]["template"]["spec"]["containers"]
    ]

    assert env["ENVIRONMENT"] == "production"
    assert env["DATABASE_SSL"] == "verify-full"
    assert images
    assert all(i.endswith(f"@{DIGEST_AGENT}") for i in images)
    assert of_kind(docs, "Job"), "the migration Job (Argo CD PreSync hook) is rendered"


# --- Criterion 3: the rendered Traefik objects (AC-18, W-9) ---------------------------------------------------------


@needs_helm
def test_given_the_rendered_production_ingress_when_searched_then_hsts_redirect_tls_minimum_and_body_cap_are_present(
    supplied_app: Path,
) -> None:
    docs = docs_of(render(APP_CHART, "app", supplied_app))
    middlewares = of_kind(docs, "Middleware")
    hsts = [m for m in middlewares if "stsSeconds" in m["spec"].get("headers", {})]
    redirects = [m for m in middlewares if "redirectScheme" in m["spec"]]
    limits = [m for m in middlewares if "buffering" in m["spec"]]
    options = of_kind(docs, "TLSOption")

    assert len(hsts) == 1
    assert hsts[0]["spec"]["headers"]["stsSeconds"] == 31536000
    assert not {"stsIncludeSubdomains", "stsPreload"} & set(hsts[0]["spec"]["headers"])
    assert len(redirects) == 1
    assert redirects[0]["spec"]["redirectScheme"] == {"scheme": "https", "permanent": True}  # port 443
    assert [m["spec"]["buffering"] for m in limits] == [{"maxRequestBodyBytes": 8192}]
    assert [o["spec"]["minVersion"] for o in options] == ["VersionTLS12"]
    assert "includeSubDomains" not in str(docs)
    assert "preload" not in str(docs).lower()


@needs_helm
def test_given_the_rendered_production_ingress_when_read_then_the_https_and_redirect_ingresses_use_the_objects(
    supplied_app: Path,
) -> None:
    docs = docs_of(render(APP_CHART, "app", supplied_app))
    prefix = "traefik.ingress.kubernetes.io/router"
    https = next(d for d in of_kind(docs, "Ingress") if d["spec"].get("tls"))
    plain = next(d for d in of_kind(docs, "Ingress") if not d["spec"].get("tls"))
    names = {
        f"default-{d['metadata']['name']}@kubernetescrd"
        for d in of_kind(docs, "Middleware") + of_kind(docs, "TLSOption")
    }

    assert https["metadata"]["annotations"][f"{prefix}.entrypoints"] == "websecure"
    assert plain["metadata"]["annotations"][f"{prefix}.entrypoints"] == "web"
    for ingress in (https, plain):
        used = ingress["metadata"]["annotations"][f"{prefix}.middlewares"].split(",")
        assert set(used) <= names
        assert ingress["spec"]["rules"][0]["host"] == "fixture.home.arpa"
    assert https["metadata"]["annotations"][f"{prefix}.tls.options"] in names
    assert https["metadata"]["annotations"]["cert-manager.io/cluster-issuer"] == "fixture-private-ca"


def test_given_the_images_when_searched_then_neither_nginx_nor_the_api_sends_hsts() -> None:
    """Exactly one HSTS header reaches the client: the one from the Traefik Middleware."""
    sources = [
        ROOT / "apps" / "web" / "nginx.conf",
        ROOT / "apps" / "web" / "snippets" / "security-headers.conf",
        *(ROOT / "backend" / "app").rglob("*.py"),
    ]
    for path in sources:
        code = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")]
        assert not any("strict-transport-security" in line.lower() for line in code), path.relative_to(ROOT)


# --- Criterion 4: nothing applies the Argo CD manifest or the production values --------------------------------------


APPLY = re.compile(r"kubectl\s+(apply|create|replace|patch|delete|rollout)|\bargocd\s|helm\s+(upgrade|install)")
TARGET = re.compile(r"deploy/argocd|envs/production|argoproj|argocd-cm")


def workflow_findings(text: str, name: str) -> list[str]:
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if APPLY.search(line):
            findings.append(f"{name}:{number} applies something to a cluster: {line.strip()}")
        if TARGET.search(line):
            findings.append(f"{name}:{number} names the Argo CD manifest or the production values: {line.strip()}")
    return findings


def test_given_the_workflows_when_searched_then_none_applies_the_argo_manifest_or_the_production_values() -> None:
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    assert files

    findings = [f for path in files for f in workflow_findings(path.read_text(encoding="utf-8"), path.name)]

    assert findings == []


@pytest.mark.parametrize(
    "line",
    [
        "run: kubectl apply -f deploy/argocd/application.yaml",
        "run: argocd app sync mail-assistant",
        "run: helm upgrade --install app deploy/charts/app -f deploy/envs/production/values.yaml",
        "run: helm template app deploy/charts/app -f deploy/envs/production/values.yaml",
        "paths: [deploy/argocd/**]",
    ],
)
def test_given_a_workflow_line_that_applies_or_names_production_when_searched_then_the_search_finds_it(
    line: str,
) -> None:
    assert workflow_findings(f"steps:\n  - {line}\n", "x.yml")


def test_given_a_workflow_line_for_the_local_values_when_searched_then_the_search_finds_nothing() -> None:
    assert (
        workflow_findings("  - run: helm lint --strict deploy/charts/app -f deploy/envs/local/values.yaml\n", "x.yml")
        == []
    )


def test_given_the_repository_when_searched_then_no_script_applies_the_argo_manifest() -> None:
    for path in [*(ROOT / "scripts").glob("*"), ROOT / "package.json"]:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "deploy/argocd" not in text, path.relative_to(ROOT).as_posix()


# --- The Argo CD manifest is a file only and keeps the human gate ---------------------------------------------------


def argo_docs() -> list[dict[str, Any]]:
    return [d for d in yaml.safe_load_all(ARGO.read_text(encoding="utf-8")) if d]


def test_given_the_argo_manifest_when_read_then_it_has_a_project_and_one_application_per_chart() -> None:
    docs = argo_docs()
    apps = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Application"}

    assert [d["kind"] for d in docs].count("AppProject") == 1
    assert set(apps) == {"mail-assistant-app", "mail-triage"}
    assert all(d["apiVersion"] == "argoproj.io/v1alpha1" for d in docs)
    sources = {n: d["spec"]["source"] for n, d in apps.items()}
    assert sources["mail-assistant-app"]["path"] == "deploy/charts/app"
    assert sources["mail-triage"]["path"] == "deploy/charts/worker"
    assert sources["mail-assistant-app"]["helm"]["valueFiles"] == ["../../envs/production/values.yaml"]
    assert sources["mail-triage"]["helm"]["valueFiles"] == ["../../envs/production/mail-triage.yaml"]
    for source in sources.values():
        assert (ROOT / source["path"] / source["helm"]["valueFiles"][0]).is_file()


def test_given_the_argo_manifest_when_read_then_sync_is_manual_and_the_project_is_narrow() -> None:
    docs = argo_docs()
    project = next(d for d in docs if d["kind"] == "AppProject")
    apps = [d for d in docs if d["kind"] == "Application"]

    for app in apps:
        assert "automated" not in app["spec"].get("syncPolicy", {}), "production is synced by a human after approval"
        assert app["spec"]["project"] == project["metadata"]["name"]
        assert app["spec"]["destination"]["namespace"] == "mail-assistant"
        assert app["spec"]["destination"]["server"] == "https://kubernetes.default.svc"
        assert app["spec"]["source"]["repoURL"] in project["spec"]["sourceRepos"]
    assert project["spec"]["sourceRepos"] == ["https://github.com/mdenhartog/mail-assistant.git"]
    assert project["spec"].get("clusterResourceWhitelist", []) == []
    assert "*" not in str(project["spec"]["destinations"])
    assert "*" not in str(project["spec"]["sourceRepos"])


@needs_helm
@pytest.mark.skipif(shutil.which("kubeconform") is None, reason="kubeconform is not installed (CI runs it)")
def test_given_the_production_render_when_checked_with_kubeconform_and_the_crd_catalog_then_it_passes(
    supplied_app: Path,
) -> None:
    catalog = "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
    result = subprocess.run(  # noqa: S603
        [
            shutil.which("kubeconform") or "",
            "-strict",
            "-summary",
            "-schema-location",
            "default",
            "-schema-location",
            catalog,
            "-",
        ],
        input=render(APP_CHART, "app", supplied_app).stdout,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
