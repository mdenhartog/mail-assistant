"""U-web-settings-41: NetworkPolicy, one replica, secrets and SMTP egress of the `app` chart.

ADR-0029, ADR-0034, ADR-0036, ADR-0037; AC-16, W-7, W-8, W-9, W-16, W-17.
"""

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
README = CHART / "README.md"
HELM = shutil.which("helm")
needs_helm = pytest.mark.skipif(HELM is None, reason="helm is needed to render the chart")
# The chart defaults name no proxy (U-web-settings-52): an environment sets them while the ingress is enabled.
PROXY = "api.config.trustedProxyCidrs={10.244.0.0/16}"
# Rendering the bare defaults: the environment must say it is not production (no digest, no alert) and name the ingress
# controller (ADR-0040: required, no default).
BARE = ("environment=local", "ingress.controller=traefik")

SECRET_ENV = {
    "APP_DATABASE_URL": "database-url",
    "APP_CODE_HASH_KEY": "code-hash-key",
    "APP_CSRF_KEY": "csrf-key",
    "APP_USERNAME_HASH_KEY": "username-hash-key",
    "APP_SMTP_USER": "smtp-user",
    "APP_SMTP_PASSWORD": "smtp-password",
}
PLAIN_ENV = (
    "APP_USERNAME",
    "APP_EMAIL_ADDRESS",
    "APP_SMTP_HOST",
    "APP_SMTP_PORT",
    "APP_SMTP_FROM",
    "APP_PUBLIC_ORIGIN",
    "APP_NOTICE_INTERVAL_MINUTES",
)


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


def of_kind(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [doc for doc in docs if doc["kind"] == kind]


def deployment(docs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(d for d in of_kind(docs, "Deployment") if d["metadata"]["name"] == f"app-{name}")


def container(docs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return deployment(docs, name)["spec"]["template"]["spec"]["containers"][0]


def local_values() -> dict[str, Any]:
    return yaml.safe_load(LOCAL_VALUES.read_text(encoding="utf-8"))


def selects(policy: dict[str, Any], name: str) -> bool:
    labels = policy["spec"]["podSelector"].get("matchLabels", {})
    return labels.get("app.kubernetes.io/name", name) == name


def egress_rules(docs: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [
        rule
        for policy in of_kind(docs, "NetworkPolicy")
        if selects(policy, name)
        for rule in policy["spec"].get("egress", [])
    ]


def ingress_rules(docs: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [
        rule
        for policy in of_kind(docs, "NetworkPolicy")
        if selects(policy, name)
        for rule in policy["spec"].get("ingress", [])
    ]


# Criterion 1: one api replica -------------------------------------------------------------------------------


@needs_helm
def test_given_the_rendered_api_deployment_when_read_then_it_has_one_replica_and_no_autoscaler() -> None:
    docs = render()

    assert deployment(docs, "api")["spec"]["replicas"] == 1
    assert not [h for h in of_kind(docs, "HorizontalPodAutoscaler") if h["metadata"]["name"] == "app-api"]


@needs_helm
def test_given_the_chart_defaults_when_rendered_then_the_api_still_has_one_replica() -> None:
    docs = render(PROXY, *BARE, values=False)

    assert deployment(docs, "api")["spec"]["replicas"] == 1
    assert not [h for h in of_kind(docs, "HorizontalPodAutoscaler") if h["metadata"]["name"] == "app-api"]


@needs_helm
@pytest.mark.parametrize(
    "setting",
    ["api.replicas=2", "api.autoscaling.enabled=true", "api.autoscaling.maxReplicas=2"],
)
def test_given_a_values_file_with_more_than_one_api_replica_when_linted_then_the_schema_refuses_it(
    setting: str,
) -> None:
    result = helm("lint", setting)

    assert result.returncode != 0, setting
    assert "api" in result.stdout + result.stderr


# Criteria 2 and 3: one ingress peer, no wide policy ---------------------------------------------------------


@needs_helm
@pytest.mark.parametrize("name", ["api", "web"])
def test_given_the_network_policy_when_read_then_ingress_has_one_peer_with_both_selectors(name: str) -> None:
    rules = ingress_rules(render(), name)

    assert rules, name
    for rule in rules:
        assert len(rule["from"]) == 1
        peer = rule["from"][0]
        assert peer["namespaceSelector"]["matchLabels"], peer
        assert peer["podSelector"]["matchLabels"], peer
        assert set(peer) == {"namespaceSelector", "podSelector"}


@needs_helm
def test_given_the_controller_values_when_rendered_then_the_peer_selects_that_namespace_and_pods() -> None:
    docs = render(
        "networkPolicy.ingressController.namespace=ingress-test",
        "networkPolicy.ingressController.podLabels.app\\.kubernetes\\.io/name=ctl",
    )
    peer = ingress_rules(docs, "api")[0]["from"][0]

    assert peer["namespaceSelector"]["matchLabels"] == {"kubernetes.io/metadata.name": "ingress-test"}
    assert peer["podSelector"]["matchLabels"] == {"app.kubernetes.io/name": "ctl"}


@needs_helm
@pytest.mark.parametrize("name", ["api", "web"])
def test_given_the_chart_defaults_when_rendered_then_the_one_peer_is_the_traefik_pods(name: str) -> None:
    docs = render(PROXY, *BARE, values=False)
    peer = ingress_rules(docs, name)[0]["from"][0]

    assert peer["namespaceSelector"]["matchLabels"] == {"kubernetes.io/metadata.name": "traefik"}
    assert peer["podSelector"]["matchLabels"] == {"app.kubernetes.io/name": "traefik"}


@needs_helm
def test_given_the_local_values_when_rendered_then_the_peer_and_the_proxy_cidr_name_the_traefik_pods() -> None:
    docs = render()
    peer = ingress_rules(docs, "api")[0]["from"][0]
    api_env = {e["name"]: e.get("value") for e in container(docs, "api")["env"]}

    assert peer["namespaceSelector"]["matchLabels"] == {"kubernetes.io/metadata.name": "traefik"}
    assert peer["podSelector"]["matchLabels"] == {"app.kubernetes.io/name": "traefik"}
    assert api_env["APP_TRUSTED_PROXY_CIDRS"] == '["10.244.0.0/16"]'  # the kind pod network of the Traefik pod


@needs_helm
def test_given_the_render_when_searched_then_no_web_to_api_rule_and_no_policy_admits_every_namespace() -> None:
    docs = render()
    policies = of_kind(docs, "NetworkPolicy")

    assert not [p for p in policies if "web-to-api" in p["metadata"]["name"]]
    for policy in policies:
        for rule in policy["spec"].get("ingress", []):
            assert "from" in rule, policy["metadata"]["name"]
            for peer in rule["from"]:
                assert peer.get("namespaceSelector") != {}, policy["metadata"]["name"]
                assert "ipBlock" not in peer
    assert not [r for r in egress_rules(docs, "web") if "app.kubernetes.io/name" in str(r)]
    assert "namespaceSelector: {}" not in helm("template").stdout


# Criterion 4: api egress ------------------------------------------------------------------------------------


@needs_helm
def test_given_the_api_egress_when_read_then_only_database_dns_and_smtp_are_allowed() -> None:
    docs = render()
    smtp = local_values()["api"]["config"]["smtp"]
    egress = local_values()["networkPolicy"]["egress"]
    destinations: set[tuple[str, int, str]] = set()
    for rule in egress_rules(docs, "api"):
        for port in rule["ports"]:
            for peer in rule["to"]:
                target = peer["ipBlock"]["cidr"] if "ipBlock" in peer else "dns"
                destinations.add((target, port["port"], port.get("protocol", "TCP")))

    assert destinations == {
        (egress["database"]["cidr"], egress["database"]["port"], "TCP"),
        (egress["smtp"]["cidr"], smtp["port"], "TCP"),
        ("dns", 53, "UDP"),
        ("dns", 53, "TCP"),
    }
    assert not [d for d in destinations if d[1] == 443]
    assert "0.0.0.0/0" not in helm("template").stdout


@needs_helm
def test_given_another_smtp_port_when_rendered_then_the_egress_rule_follows_the_value() -> None:
    docs = render("api.config.smtp.port=2525")

    ports = {p["port"] for rule in egress_rules(docs, "api") for p in rule["ports"]}
    assert 2525 in ports
    assert local_values()["api"]["config"]["smtp"]["port"] not in ports - {2525}


@needs_helm
@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("networkPolicy.egress.smtp.cidr=0.0.0.0/0", "cidr"),
        ("networkPolicy.egress.database.cidr=0.0.0.0/0", "cidr"),
        ("networkPolicy.egress.smtp.cidr=10.0.0.0/8", "cidr"),
        ("api.config.smtp.port=443", "port"),
        ("networkPolicy.egress.database.port=443", "port"),
    ],
)
def test_given_a_wide_or_https_egress_value_when_linted_then_it_fails(setting: str, expected: str) -> None:
    result = helm("lint", setting)

    assert result.returncode != 0, setting
    assert expected in result.stdout + result.stderr


# Criterion 5: secrets by reference --------------------------------------------------------------------------


@needs_helm
def test_given_the_api_env_when_read_then_secrets_are_references_to_the_release_secret() -> None:
    env = {e["name"]: e for e in container(render(), "api")["env"]}

    for name, key in SECRET_ENV.items():
        assert env[name] == {"name": name, "valueFrom": {"secretKeyRef": {"name": "app-api", "key": key}}}, name


@needs_helm
def test_given_the_api_env_when_read_then_the_plain_settings_come_from_values() -> None:
    env = {e["name"]: e.get("value") for e in container(render(), "api")["env"]}
    config = local_values()["api"]["config"]

    for name in PLAIN_ENV:
        assert env[name], name
    assert env["APP_SMTP_FROM"] == config["smtp"]["from"]
    assert env["APP_SMTP_HOST"] == config["smtp"]["host"]
    assert env["APP_SMTP_PORT"] == str(config["smtp"]["port"])
    assert env["APP_PUBLIC_ORIGIN"] == config["publicOrigin"]
    assert env["APP_ENVIRONMENT"] == "production"
    assert "@" in env["APP_SMTP_FROM"]


@needs_helm
def test_given_the_render_when_searched_then_no_secret_value_sits_in_a_literal_or_a_configmap() -> None:
    docs = render()
    api_env = container(docs, "api")["env"]

    assert not of_kind(docs, "ConfigMap")
    assert not of_kind(docs, "Secret")
    assert [e["name"] for e in api_env if "value" in e and re.search(r"KEY|PASSWORD|URL|SMTP_USER", e["name"])] == []
    assert "valueFrom" not in str(container(docs, "web"))


def values_files() -> list[Path]:
    deploy = ROOT / "deploy"
    return [*deploy.glob("charts/app/values.yaml"), *deploy.glob("envs/**/*.yaml")]


def test_given_the_values_files_when_searched_then_no_secret_key_or_credential_is_in_them() -> None:
    for path in values_files():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"postgres(ql)?(\+\w+)?://\S+:\S+@", text), path
        assert not re.search(r"(password|hashKey|csrfKey|databaseUrl|smtpUser)\s*:", text, re.IGNORECASE), path
        assert "secretKeyRef" not in data


# Criterion 6: no weakened TLS words, README documents verify-full -------------------------------------------


def chart_files() -> list[Path]:
    return [p for p in CHART.rglob("*") if p.is_file()]


def test_given_the_chart_and_readme_when_searched_then_no_tls_weakening_words_appear() -> None:
    assert README in chart_files()
    for path in chart_files():
        text = path.read_text(encoding="utf-8")
        for word in ("sslmode=disable", "verify-none", "insecure", "SSL_CERT_FILE"):
            assert word.lower() not in text.lower(), (path, word)


def test_given_the_readme_when_read_then_it_documents_the_asyncpg_ssl_verify_full_setting() -> None:
    text = README.read_text(encoding="utf-8")

    assert "ssl=verify-full" in text
    assert "asyncpg" in text
    assert "sslmode" not in text.replace("`sslmode`", "")


# Criterion 7: certificate expiry alert ----------------------------------------------------------------------


@needs_helm
def test_given_the_cert_alert_is_off_when_rendered_then_no_prometheus_rule_exists() -> None:
    assert not of_kind(render(), "PrometheusRule")
    assert not of_kind(render(PROXY, *BARE, values=False), "PrometheusRule")


@needs_helm
def test_given_the_cert_alert_is_on_when_rendered_then_a_14_day_expiry_rule_exists() -> None:
    rules = of_kind(render("certAlert.enabled=true"), "PrometheusRule")

    assert len(rules) == 1
    rule = rules[0]["spec"]["groups"][0]["rules"][0]
    assert rule["alert"] == "AppCertificateExpiresSoon"
    assert "certmanager_certificate_expiration_timestamp_seconds" in rule["expr"]
    assert 'name="app-tls"' in rule["expr"]
    assert str(14 * 24 * 3600) in rule["expr"]


@needs_helm
def test_given_fewer_than_14_days_ahead_when_linted_then_it_fails() -> None:
    result = helm("lint", "certAlert.enabled=true", "certAlert.daysAhead=7")

    assert result.returncode != 0
    assert "daysAhead" in result.stdout + result.stderr


# Criterion 8: sealing steps in the README -------------------------------------------------------------------


def test_given_the_readme_when_checked_then_sealing_uses_standard_input_and_lists_the_keys() -> None:
    text = README.read_text(encoding="utf-8")

    assert "--from-literal" not in text
    assert "kubeseal" in text
    assert "--raw" in text
    assert "SealedSecret" in text
    for key in SECRET_ENV.values():
        assert f"`{key}`" in text, key
    for setting in ("smtp_from", "APP_SMTP_FROM"):
        assert setting in text, setting


# Criterion 9: lint, kubeconform, kube-linter, probes and hardening ------------------------------------------


@needs_helm
def test_given_the_local_values_when_linted_strictly_then_the_chart_has_no_findings() -> None:
    result = helm("lint")

    assert result.returncode == 0, result.stdout + result.stderr


@needs_helm
def test_given_the_api_container_when_read_then_probes_and_hardening_are_set() -> None:
    api = container(render(), "api")

    assert api["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert api["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert api["securityContext"]["readOnlyRootFilesystem"] is True
    assert api["securityContext"]["allowPrivilegeEscalation"] is False
    assert deployment(render(), "api")["spec"]["template"]["spec"]["securityContext"]["runAsNonRoot"] is True


@needs_helm
@pytest.mark.skipif(shutil.which("kubeconform") is None, reason="kubeconform is not installed (CI runs it)")
def test_given_the_rendered_chart_when_checked_with_kubeconform_then_it_passes() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("kubeconform") or "", "-strict", "-summary", "-"],
        input=helm("template").stdout,
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
