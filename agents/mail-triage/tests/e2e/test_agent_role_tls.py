"""U-web-settings-58 (SEC-10, W-8, W-9): the agent roles reach the prod-like database over TLS only.

Run by the `prod-like` CI job after the migrate service and ``docker compose --profile prod-like up -d --build --wait``,
from the repository root:

    E2E_PROD_LIKE=1 uv run --frozen --project agents/mail-triage pytest --no-cov agents/mail-triage/tests/e2e

The role connects to the host name ``db`` (the job adds it to /etc/hosts) with the agent's own TLS argument, checked
against the private CA of ``deploy/prod-like/certs.sh``. It needs ``MAIL_TRIAGE_RUNTIME_PASSWORD`` and
``POSTGRES_PASSWORD`` in the environment; no password is written in this file.
"""

from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pytest

from app.db.engine import ssl_argument

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_PROD_LIKE"), reason="needs the running prod-like stack")

ROOT = Path(__file__).resolve().parents[4]
CA = ROOT / "deploy" / "prod-like" / "certs" / "ca.crt"
AGENT_ROLE = "mail_triage_runtime"
OWNER_ROLE = "app"


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        pytest.fail(f"{name} must be set to the value the stack was started with")  # a gate: fail, never skip
    return value


async def _connect(role: str, password: str, tls: object) -> asyncpg.Connection:
    return await asyncpg.connect(
        host="db",
        port=int(os.environ.get("DB_PORT", "5432")),
        user=role,
        password=password,
        database="app",
        ssl=tls,  # type: ignore[arg-type]
        timeout=15,
    )


async def test_given_the_agent_role_connecting_without_tls_when_it_tries_then_the_server_refuses() -> None:
    with pytest.raises(asyncpg.InvalidAuthorizationSpecificationError, match=r"(?i)pg_hba\.conf rejects"):
        await _connect(AGENT_ROLE, _require("MAIL_TRIAGE_RUNTIME_PASSWORD"), False)


async def test_given_the_owner_role_connecting_without_tls_when_it_tries_then_the_server_refuses() -> None:
    with pytest.raises(asyncpg.InvalidAuthorizationSpecificationError, match=r"(?i)pg_hba\.conf rejects"):
        await _connect(OWNER_ROLE, _require("POSTGRES_PASSWORD"), False)


async def test_given_the_agent_role_with_verify_full_and_the_ca_when_it_connects_then_the_session_uses_tls() -> None:
    connection = await _connect(AGENT_ROLE, _require("MAIL_TRIAGE_RUNTIME_PASSWORD"), ssl_argument("verify-full", str(CA)))
    try:
        row = await connection.fetchrow("select ssl, version from pg_stat_ssl where pid = pg_backend_pid()")
    finally:
        await connection.close()

    assert row is not None
    assert row["ssl"] is True
    assert row["version"] in {"TLSv1.2", "TLSv1.3"}
