"""U-web-settings-38 (AC-29, W-14, AC-4): the mail catcher and the api of the running prod-like stack.

Image level, run by the `prod-like` CI job after ``deploy/prod-like/certs.sh``, the migrate service and
``docker compose --profile prod-like up -d --build --wait``:

    uv run --project backend pytest --no-cov backend/tests/e2e

Needs ``E2E_PROD_LIKE=1`` and ``mail-assistant.localhost`` resolving to 127.0.0.1 (the job adds it to /etc/hosts).
The catcher is read over its HTTP interface on 127.0.0.1:${MAIL_PORT}.
"""

import os
import re
import subprocess
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_PROD_LIKE"), reason="needs the running prod-like stack")

ROOT = Path(__file__).resolve().parents[3]
CA = ROOT / "deploy" / "prod-like" / "certs" / "ca.crt"
EDGE = f"https://mail-assistant.localhost:{os.environ.get('EDGE_HTTPS_PORT', '8443')}"
MAILBOX = f"http://127.0.0.1:{os.environ.get('MAIL_PORT', '8025')}"
USERNAME = os.environ.get("E2E_USERNAME", "e2e-owner")
COMPOSE = ["docker", "compose", "--profile", "prod-like"]
REFUSE_STARTTLS = ROOT / "deploy" / "prod-like" / "mail-no-starttls.yaml"
CODE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
SMTP_FIELDS = ("APP_SMTP_HOST", "APP_SMTP_PORT", "APP_SMTP_FROM", "APP_SMTP_USER", "APP_SMTP_PASSWORD")


def _run(*command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=check, timeout=240)  # noqa: S603


def _request_code() -> httpx.Response:
    with httpx.Client(verify=str(CA), base_url=EDGE, timeout=20) as edge:
        return edge.post("/auth/request-code", json={"username": USERNAME}, headers={"Origin": EDGE})


def _messages() -> list[dict[str, object]]:
    return httpx.get(f"{MAILBOX}/api/v1/messages", timeout=10).json()["messages"]


def _wait_for_messages(count: int, seconds: float = 20.0) -> list[dict[str, object]]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = _messages()
        if len(found) >= count:
            return found
        time.sleep(0.5)
    return _messages()


@pytest.fixture(autouse=True)
def empty_mailbox() -> None:
    httpx.delete(f"{MAILBOX}/api/v1/messages", timeout=10)
    time.sleep(2)  # the resend cooldown of the prod-like profile is one second


def test_given_a_code_request_through_the_edge_when_the_api_sends_then_the_catcher_holds_one_message() -> None:
    response = _request_code()
    found = _wait_for_messages(1)

    assert response.status_code == 200
    assert len(found) == 1
    detail = httpx.get(f"{MAILBOX}/api/v1/message/{found[0]['ID']}", timeout=10).json()
    assert CODE.search(detail["Text"])
    assert not CODE.search(detail["Subject"])


def test_given_the_catcher_when_a_client_skips_starttls_then_it_is_refused_and_with_the_ca_it_is_accepted() -> None:
    script = (
        "import smtplib, ssl\n"
        "plain = smtplib.SMTP('mail', 1025, timeout=10)\n"
        "plain.ehlo()\n"
        "code, _ = plain.docmd('MAIL FROM:<a@example.test>')\n"
        "assert code == 530, code\n"
        "plain.close()\n"
        "tls = smtplib.SMTP('mail', 1025, timeout=10)\n"
        "tls.ehlo()\n"
        "tls.starttls(context=ssl.create_default_context(cafile='/certs/ca.crt'))\n"
        "tls.close()\n"
    )

    result = _run(*COMPOSE, "exec", "-T", "api", "python", "-c", script, check=False)

    assert result.returncode == 0, result.stderr


def test_given_a_catcher_without_starttls_when_a_code_is_requested_then_nothing_arrives_and_success_is_answered() -> (
    None
):
    override = ["-f", "compose.yaml", "-f", str(REFUSE_STARTTLS)]
    try:
        _run(*COMPOSE, *override, "up", "-d", "--no-deps", "--force-recreate", "--wait", "mail")
        time.sleep(2)
        response = _request_code()
        time.sleep(5)
        held = _messages()
        logs = _run(*COMPOSE, "logs", "--no-color", "api").stdout
    finally:
        _run(*COMPOSE, "up", "-d", "--no-deps", "--force-recreate", "--wait", "mail")

    assert response.status_code == 200
    assert held == []
    assert "mail send failed" in logs
    assert "code" not in response.text.lower()  # the answer carries no code (a timestamp has six digits, too)


@pytest.mark.parametrize("missing", SMTP_FIELDS)
def test_given_the_api_image_with_a_missing_smtp_setting_when_it_starts_then_it_stops_and_names_the_field(
    missing: str,
) -> None:
    environment = {
        "APP_ENVIRONMENT": "production",
        "APP_USERNAME": "image-user",
        "APP_EMAIL_ADDRESS": "owner@example.test",
        "APP_SMTP_HOST": "mail",
        "APP_SMTP_PORT": "1025",
        "APP_SMTP_FROM": "assistant@example.test",
        "APP_SMTP_USER": "image-smtp-user",
        "APP_SMTP_PASSWORD": "image-smtp-password",
        "APP_CODE_HASH_KEY": "a" * 32,
        "APP_CSRF_KEY": "b" * 32,
        "APP_USERNAME_HASH_KEY": "c" * 32,
        "APP_PUBLIC_ORIGIN": "https://mail-assistant.localhost:8443",
        "APP_DATABASE_URL": "postgresql+asyncpg://web:image-db-password@db:5432/app",
    }
    del environment[missing]
    flags = [item for name, value in environment.items() for item in ("-e", f"{name}={value}")]

    result = _run("docker", "run", "--rm", *flags, "mail-assistant-api:local", check=False)

    field = missing.removeprefix("APP_").lower()
    assert result.returncode != 0
    assert field in result.stdout + result.stderr
    assert "image-smtp-password" not in result.stdout + result.stderr
