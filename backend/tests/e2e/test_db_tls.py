"""U-web-settings-39 (W-8, W-9, AC-17): the TLS database of the running prod-like stack.

Image level, run by the `e2e` CI job after ``deploy/prod-like/certs.sh``, the migrate service and
``docker compose --profile prod-like up -d --build --wait``:

    uv run --project backend pytest --no-cov backend/tests/e2e

Needs ``E2E_PROD_LIKE=1`` (otherwise the module is skipped, so ``uv run pytest`` in backend/ stays unit-only),
``POSTGRES_PASSWORD`` and ``WEB_ROLE_PASSWORD`` in the environment, and ``db`` resolving to 127.0.0.1 (the job adds it
to /etc/hosts; the certificate carries the name ``db`` only). No password is written in this file.
"""

import datetime as dt
import os
import ssl
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.db import build_ssl_context

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_PROD_LIKE"), reason="needs the running prod-like stack")

ROOT = Path(__file__).resolve().parents[3]
CERTS = ROOT / "deploy" / "prod-like" / "certs"
WEB_ROLE = "web_settings_runtime"
PORT = int(os.environ.get("DB_PORT", "5432"))


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        pytest.fail(f"{name} must be set to the value the stack was started with")  # a gate: fail, never skip
    return value


async def _connect(host: str, ssl_arg: ssl.SSLContext | bool, user: str, password: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=host, port=PORT, user=user, password=password, database="app", ssl=ssl_arg, timeout=15
    )


def _throwaway_ca_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "other CA")])
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
async def web() -> AsyncIterator[asyncpg.Connection]:
    context = build_ssl_context("verify-full", str(CERTS / "ca.crt"))
    connection = await _connect("db", context, WEB_ROLE, _require("WEB_ROLE_PASSWORD"))
    yield connection
    await connection.close()


async def test_given_the_stack_when_the_engine_connects_as_the_web_role_then_the_connection_is_tls_1_2_or_newer(
    web: asyncpg.Connection,
) -> None:
    row = await web.fetchrow("SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid()")

    assert row is not None
    assert row["ssl"] is True
    assert row["version"] in {"TLSv1.2", "TLSv1.3"}


async def test_given_an_alias_not_in_the_certificate_when_the_engine_connects_then_the_host_name_is_rejected() -> None:
    context = build_ssl_context("verify-full", str(CERTS / "ca.crt"))

    with pytest.raises(ssl.SSLCertVerificationError, match=r"(?i)hostname|IP address"):
        await _connect("127.0.0.1", context, WEB_ROLE, _require("WEB_ROLE_PASSWORD"))


async def test_given_a_ca_that_did_not_sign_the_server_when_the_engine_connects_then_it_is_rejected(
    tmp_path: Path,
) -> None:
    other_ca = tmp_path / "other-ca.crt"
    other_ca.write_text(_throwaway_ca_pem())
    context = build_ssl_context("verify-full", str(other_ca))

    with pytest.raises(ssl.SSLCertVerificationError, match=r"(?i)certificate verify failed"):
        await _connect("db", context, WEB_ROLE, _require("WEB_ROLE_PASSWORD"))


async def test_given_a_plain_connection_as_the_web_role_when_made_then_the_server_refuses_it() -> None:
    with pytest.raises(asyncpg.InvalidAuthorizationSpecificationError, match=r"(?i)pg_hba\.conf rejects"):
        await _connect("db", False, WEB_ROLE, _require("WEB_ROLE_PASSWORD"))


async def test_given_the_migrate_service_ran_when_roles_are_listed_then_both_exist_without_privileges() -> None:
    owner = await _connect(
        "db", build_ssl_context("verify-full", str(CERTS / "ca.crt")), "app", _require("POSTGRES_PASSWORD")
    )
    try:
        roles = {
            row["rolname"]: row
            for row in await owner.fetch(
                "SELECT rolname, rolsuper, rolcreaterole, rolreplication FROM pg_roles WHERE rolname = ANY($1::text[])",
                [WEB_ROLE, "mail_triage_runtime"],
            )
        }
    finally:
        await owner.close()

    assert set(roles) == {WEB_ROLE, "mail_triage_runtime"}
    assert not any(role["rolsuper"] or role["rolcreaterole"] or role["rolreplication"] for role in roles.values())
