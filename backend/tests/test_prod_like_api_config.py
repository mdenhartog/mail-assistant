"""U-web-settings-38: file-level checks of the prod-like api service, the mail catcher and the chart env names.

What only a running stack proves (STARTTLS on the wire, the refused STARTTLS, the missing setting in the image) is
checked by ``tests/e2e/test_mail_tls.py`` in the `e2e` CI job.
"""

import re
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
CHART = ROOT / "deploy" / "charts" / "app"
MAIL_TLS = ROOT / "deploy" / "prod-like" / "mail-tls.sh"
CERTS = ROOT / "deploy" / "prod-like" / "certs.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RAISED_LIMITS = (
    "APP_RATE_LIMIT_PER_MINUTE",
    "APP_RESEND_COOLDOWN_SECONDS",
    "APP_CODES_PER_HOUR",
    "APP_OPEN_LOGIN_REQUEST_CAP",
)
SENSITIVE = re.compile(r"PASSWORD|_KEY|SECRET|DATABASE_URL")
APP_NAME = re.compile(r"\bAPP_[A-Z][A-Z_]*\b")
REFERENCE = re.compile(r"\$\{[A-Z_]+(:\?[^}]*|:-[^}]*)?\}")


def services() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def field_names() -> set[str]:
    return {f"APP_{name.upper()}" for name in Settings.model_fields}


# --- criterion 4: the api service environment ---


def test_given_the_api_service_when_read_then_every_sensitive_value_is_a_reference() -> None:
    environment = services()["api"]["environment"]
    sensitive = {name: str(value) for name, value in environment.items() if SENSITIVE.search(name)}

    assert {"APP_SMTP_PASSWORD", "APP_CODE_HASH_KEY", "APP_CSRF_KEY", "APP_USERNAME_HASH_KEY"} <= set(sensitive)
    for name, value in sensitive.items():
        assert REFERENCE.search(value), name
        if name != "APP_DATABASE_URL":  # the URL keeps its scheme, role and host; its password is the reference
            assert not re.sub(r"\$\{[^}]*\}", "", value), f"{name} has a literal part"


def test_given_the_api_service_when_read_then_it_points_at_the_catcher_and_trusts_the_internal_ca() -> None:
    api = services()["api"]
    environment = api["environment"]

    assert environment["APP_SMTP_HOST"] == "mail"
    assert environment["SSL_CERT_FILE"] == "/certs/ca.crt"
    assert "./deploy/prod-like/certs/ca.crt:/certs/ca.crt:ro" in api["volumes"]
    assert environment["APP_PUBLIC_ORIGIN"].startswith("https://mail-assistant.localhost:")
    assert "APP_SMTP_FROM" in environment
    assert "APP_SMTP_STARTTLS" not in environment  # the default is on and nothing in compose can turn it off
    assert not any("VERIFY" in name or "INSECURE" in name for name in environment)


def test_given_the_api_service_when_read_then_it_waits_for_the_catcher() -> None:
    assert "mail" in services()["api"]["depends_on"]


def test_given_the_raised_e2e_limits_when_read_then_they_exist_in_the_prod_like_api_service() -> None:
    environment = services()["api"]["environment"]

    for name in RAISED_LIMITS:
        assert name in environment, name


# --- criterion 5: no raised limits in the default and dev profiles ---


def test_given_the_default_and_dev_profiles_when_read_then_the_raised_limits_are_not_set() -> None:
    for name, service in services().items():
        if name == "api":
            continue
        text = yaml.safe_dump(service)
        for limit in RAISED_LIMITS:
            assert limit not in text, f"{name} sets {limit}"


def test_given_the_services_without_a_profile_when_read_then_only_the_database_runs_by_default() -> None:
    always = {name for name, service in services().items() if not service.get("profiles")}

    assert "db" in always
    assert not {"api", "mail"} & always  # the catcher belongs to prod-like


# --- the mail catcher ---


def test_given_the_mail_service_when_read_then_it_requires_starttls_with_the_ca_signed_certificate_and_a_login() -> (
    None
):
    mail = services()["mail"]
    environment = mail["environment"]

    assert str(environment["MP_SMTP_REQUIRE_STARTTLS"]).lower() in {"true", "1"}
    assert environment["MP_SMTP_TLS_CERT"] == "/certs/mail.crt"
    assert environment["MP_SMTP_TLS_KEY"] == "/certs/mail.key"
    assert "./deploy/prod-like/certs:/certs:ro" in mail["volumes"]
    assert "${" in str(environment["MP_SMTP_AUTH"])  # the send-only credential is a reference
    assert "MP_SMTP_AUTH_ACCEPT_ANY" not in environment
    assert all(str(port).startswith("127.0.0.1:") for port in mail["ports"])
    assert mail["image"].startswith("axllent/mailpit:v")


def test_given_the_compose_file_when_searched_then_no_credential_is_a_literal() -> None:
    raw = COMPOSE.read_text(encoding="utf-8")

    assert not re.search(r"(?m)^\s*(\w*PASSWORD\w*|\w*_KEY|MP_SMTP_AUTH):\s+(?!\$\{|\"|/certs/)\S", raw)


def test_given_the_certs_script_when_read_then_it_makes_the_mail_leaf_through_mail_tls() -> None:
    text = CERTS.read_text(encoding="utf-8")

    assert "mail-tls.sh" in text
    assert text.count('-CA "$out/ca.crt" -CAkey "$work/ca.key"') == 2  # the edge and database leaves, as before


def test_given_the_mail_tls_script_when_read_then_it_signs_a_leaf_for_the_host_name_mail() -> None:
    text = MAIL_TLS.read_text(encoding="utf-8")

    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "DNS:mail" in text
    assert "mail.crt" in text
    assert "mail.key" in text
    assert "serverAuth" in text
    assert "-CAkey" in text
    assert "BEGIN" not in text


# --- the chart env names against the settings ---


def test_given_the_chart_when_its_env_names_are_listed_then_every_one_is_a_backend_setting() -> None:
    names: set[str] = set()
    for path in (CHART / "templates" / "workloads.yaml", CHART / "values.yaml"):
        names |= set(APP_NAME.findall(path.read_text(encoding="utf-8")))

    assert {"APP_SMTP_FROM", "APP_DATABASE_URL", "APP_ENVIRONMENT"} <= names
    assert names - field_names() == set(), "chart env names that the backend does not read"


def test_given_the_compose_api_service_when_its_env_names_are_listed_then_every_app_name_is_a_backend_setting() -> None:
    names = {name for name in services()["api"]["environment"] if name.startswith("APP_")}

    assert names - field_names() == set()


def test_given_the_chart_when_compared_with_the_settings_then_every_required_setting_is_passed() -> None:
    chart = (CHART / "templates" / "workloads.yaml").read_text(encoding="utf-8")
    required = {
        "username",
        "email_address",
        "smtp_host",
        "smtp_port",
        "smtp_from",
        "smtp_user",
        "smtp_password",
        "code_hash_key",
        "csrf_key",
        "username_hash_key",
        "public_origin",
        "database_url",
    }

    assert {f"APP_{name.upper()}" for name in required} <= set(APP_NAME.findall(chart))


# --- the CI job ---


def test_given_the_e2e_job_when_read_then_the_env_file_carries_the_new_references_and_the_catcher_tests_run() -> None:
    job = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["e2e"]
    steps = "\n".join(str(step.get("run", "")) for step in job["steps"])

    for name in ("MAIL_SMTP_PASSWORD", "APP_CODE_HASH_KEY", "APP_CSRF_KEY", "APP_USERNAME_HASH_KEY"):
        assert name in steps, name
    assert "mail-assistant.localhost" in steps  # the python tests resolve the edge name
    assert "backend/tests/e2e" in steps
