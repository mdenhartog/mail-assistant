"""U-web-settings-09: the real driver against a TLS PostgreSQL with a throwaway CA and server certificate (W-8, W-9).

``verify-full`` must reject a wrong host name and an untrusted CA; ``verify-ca`` shows that the host name check is what
rejected the wrong host.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from app.db import Database, DatabaseUnavailable, build_ssl_context
from tests.db.conftest import report_start_failure

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

IMAGE = "postgres:16-alpine"
GOOD_HOST = "localhost"  # the only name in the server certificate
WRONG_HOST = "127.0.0.1"  # reaches the same server, but is not in the certificate

_ENTRYPOINT = (
    'printf "%s" "$TLS_CRT" > /tmp/server.crt; printf "%s" "$TLS_KEY" > /tmp/server.key; '
    "chown postgres /tmp/server.crt /tmp/server.key; chmod 600 /tmp/server.key; "
    "exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/tmp/server.crt -c ssl_key_file=/tmp/server.key"
)


@dataclass(frozen=True)
class Authority:
    key: ec.EllipticCurvePrivateKey
    certificate: x509.Certificate

    @property
    def pem(self) -> str:
        return self.certificate.public_bytes(serialization.Encoding.PEM).decode()


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _validity() -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    return start, start + dt.timedelta(days=2)


def make_authority(common_name: str) -> Authority:
    key = ec.generate_private_key(ec.SECP256R1())
    start, end = _validity()
    certificate = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(_name(common_name))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return Authority(key, certificate)


def make_server_pems(authority: Authority, host: str) -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    start, end = _validity()
    certificate = (
        x509.CertificateBuilder()
        .subject_name(_name(host))
        .issuer_name(authority.certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(authority.key.public_key()), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(authority.key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return certificate.public_bytes(serialization.Encoding.PEM).decode(), key_pem


@dataclass(frozen=True)
class TlsServer:
    port: int
    user: str
    password: str
    database: str
    trusted_ca: Path
    other_ca: Path

    def url(self, host: str) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{host}:{self.port}/{self.database}"


@pytest.fixture(scope="module")
def tls_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TlsServer]:
    trusted, other = make_authority("test-ca"), make_authority("test-other-ca")
    certificate, key = make_server_pems(trusted, GOOD_HOST)
    container = (
        PostgresContainer(IMAGE, driver=None)
        .with_env("TLS_CRT", certificate)
        .with_env("TLS_KEY", key)
        .with_kwargs(entrypoint=["sh", "-c", _ENTRYPOINT, "sh"])
    )
    try:
        container.start()
    except Exception as error:
        report_start_failure(error, IMAGE, os.environ)
    directory = tmp_path_factory.mktemp("tls")
    (directory / "trusted.pem").write_text(trusted.pem, encoding="ascii")
    (directory / "other.pem").write_text(other.pem, encoding="ascii")
    yield TlsServer(
        port=int(container.get_exposed_port(5432)),
        user=container.username,
        password=container.password,
        database=container.dbname,
        trusted_ca=directory / "trusted.pem",
        other_ca=directory / "other.pem",
    )
    container.stop()


async def _select_one(server: TlsServer, host: str, mode: str, ca: Path) -> int:
    database = Database.create(
        server.url(host), ssl_context=build_ssl_context(mode, str(ca)), statement_timeout_ms=5000
    )
    try:
        async with database.session() as session:
            return (await session.execute(text("select 1"))).scalar_one()
    finally:
        await database.dispose()


async def test_given_the_right_host_and_ca_when_verify_full_then_the_connection_is_tls(tls_server: TlsServer) -> None:
    database = Database.create(
        tls_server.url(GOOD_HOST),
        ssl_context=build_ssl_context("verify-full", str(tls_server.trusted_ca)),
        statement_timeout_ms=5000,
    )
    try:
        async with database.session() as session:
            used = (
                await session.execute(text("select ssl from pg_stat_ssl where pid = pg_backend_pid()"))
            ).scalar_one()
    finally:
        await database.dispose()

    assert used is True


async def test_given_a_wrong_host_name_when_verify_full_then_the_connection_is_rejected(tls_server: TlsServer) -> None:
    with pytest.raises(DatabaseUnavailable) as raised:
        await _select_one(tls_server, WRONG_HOST, "verify-full", tls_server.trusted_ca)

    assert "Cert" in raised.value.error_class or "SSL" in raised.value.error_class


async def test_given_an_untrusted_ca_when_verify_full_then_the_connection_is_rejected(tls_server: TlsServer) -> None:
    with pytest.raises(DatabaseUnavailable) as raised:
        await _select_one(tls_server, GOOD_HOST, "verify-full", tls_server.other_ca)

    assert "Cert" in raised.value.error_class or "SSL" in raised.value.error_class


async def test_given_an_untrusted_ca_when_verify_ca_then_the_connection_is_rejected(tls_server: TlsServer) -> None:
    with pytest.raises(DatabaseUnavailable):
        await _select_one(tls_server, GOOD_HOST, "verify-ca", tls_server.other_ca)


async def test_given_a_wrong_host_name_when_verify_ca_then_only_the_host_check_is_missing(
    tls_server: TlsServer,
) -> None:
    assert await _select_one(tls_server, WRONG_HOST, "verify-ca", tls_server.trusted_ca) == 1
