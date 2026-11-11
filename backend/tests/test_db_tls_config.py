"""U-web-settings-39: file-level checks of the prod-like TLS database (W-8, W-9, AC-17).

What only a running stack proves (TLS on the wire, host name and CA rejection, the plain refusal) is checked by
``tests/e2e/test_db_tls.py`` in the `e2e` CI job, which also greps the rendered `docker compose config` for a password.
Here the compose file, the scripts and the workflow are parsed as files.
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
PROD_LIKE = ROOT / "deploy" / "prod-like"
DB_TLS = PROD_LIKE / "db-tls.sh"
HBA = PROD_LIKE / "pg_hba.conf"
CERTS = PROD_LIKE / "certs.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
WEB_ROLE = "web_settings_runtime"


def services() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def e2e_run_text() -> str:
    job = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["e2e"]
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


# --- criterion 6: no literal password in compose (the CI job repeats it on the rendered `docker compose config`) ---


def test_given_the_compose_file_when_searched_then_a_password_is_never_a_literal() -> None:
    raw = COMPOSE.read_text(encoding="utf-8")

    assert not re.search(r"://[^:\s/]+:(?!\$\{)[^@\s/]+@", raw)
    assert not re.search(r"PASSWORD\w*\s*[:=]\s*(?!\$\{)\S", raw)


def test_given_the_e2e_job_when_read_then_it_greps_the_rendered_config_for_a_password() -> None:
    steps = e2e_run_text()

    assert "--profile prod-like config" in steps
    assert "tests/e2e/test_db_tls.py" in steps or "backend/tests/e2e" in steps


# --- the database service ---


def test_given_the_db_service_when_read_then_it_serves_tls_through_the_wrapper_with_the_hba_file() -> None:
    db = services()["db"]
    volumes = "\n".join(db["volumes"])

    assert "./deploy/prod-like/db-tls.sh:" in volumes
    assert "./deploy/prod-like/pg_hba.conf:" in volumes
    assert "./deploy/prod-like/certs:" in volumes
    assert all(mount.endswith(":ro") for mount in db["volumes"] if mount.startswith("./deploy/"))
    assert "db-tls.sh" in " ".join(db["entrypoint"])
    assert all(str(port).startswith("127.0.0.1:") for port in db["ports"])


def test_given_the_db_wrapper_when_read_then_it_turns_tls_on_with_a_private_key_copy_and_modern_tls() -> None:
    text = DB_TLS.read_text(encoding="utf-8")

    assert text.startswith("#!/bin/sh")
    assert "set -eu" in text
    assert "chmod 0600" in text
    assert "chown postgres" in text
    assert "ssl=on" in text
    assert "ssl_min_protocol_version=TLSv1.2" in text
    assert "hba_file" in text
    assert "docker-entrypoint.sh" in text
    assert "BEGIN" not in text


def test_given_the_hba_file_when_read_then_the_web_role_gets_tls_only_and_scram() -> None:
    lines = [ln.split() for ln in HBA.read_text(encoding="utf-8").splitlines() if ln.strip() and ln[0] != "#"]
    rules = {(row[0], row[2]): row[-1] for row in lines}

    assert rules[("hostssl", WEB_ROLE)] == "scram-sha-256"
    assert rules[("hostnossl", WEB_ROLE)] == "reject"
    order = [(row[0], row[2]) for row in lines]
    assert order.index(("hostnossl", WEB_ROLE)) < order.index(("host", "all"))
    assert not any(row[-1] in {"trust", "password", "md5"} for row in lines)


def test_given_the_certs_script_when_read_then_it_signs_a_database_leaf_for_db_with_the_same_ca() -> None:
    text = CERTS.read_text(encoding="utf-8")

    assert "DNS:db" in text
    assert "db.crt" in text
    assert "db.key" in text
    assert text.count('-CA "$out/ca.crt" -CAkey "$work/ca.key"') == 2  # the edge leaf and the database leaf


# --- the api uses the web role with verify-full ---


def test_given_the_api_service_when_read_then_it_connects_as_the_web_role_with_verify_full_and_the_ca() -> None:
    api = services()["api"]
    env = api["environment"]

    assert env["APP_DATABASE_URL"].startswith(f"postgresql+asyncpg://{WEB_ROLE}:${{WEB_ROLE_PASSWORD")
    assert env["APP_DATABASE_URL"].endswith("@db:5432/app")
    assert env["APP_DATABASE_SSL"] == "verify-full"
    assert env["APP_DATABASE_CA_FILE"] == "/certs/ca.crt"
    assert "./deploy/prod-like/certs/ca.crt:/certs/ca.crt:ro" in api["volumes"]
    assert "sslmode" not in env["APP_DATABASE_URL"]


def test_given_the_runtime_services_when_read_then_none_has_the_owner_credentials() -> None:
    for name, service in services().items():
        if name in {"db", "mail-triage-migrate"}:
            continue
        text = yaml.safe_dump(service)
        assert "POSTGRES_PASSWORD" not in text, name
        assert "app:${" not in text, name  # the owner role is `app`


# --- the CI job ---


def test_given_the_e2e_job_when_read_then_it_migrates_before_up_and_then_runs_the_image_level_tests() -> None:
    steps = e2e_run_text()

    assert "WEB_ROLE_PASSWORD" in steps
    assert "mail-triage-migrate" in steps
    assert steps.index("mail-triage-migrate") < steps.index("up -d --build --wait")
    assert "backend/tests/e2e" in steps
    assert "--no-cov" in steps
    assert "readyz" in steps
