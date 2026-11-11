"""A real local SMTP server for adapter tests: STARTTLS, certificates from a throwaway CA, recorded events."""

import asyncio
import datetime as dt
import ipaddress
import socket
import ssl
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, AuthResult, Envelope, Session
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

HOST = "127.0.0.1"
USER = "send-only@example.test"
PASSWORD = "canary-smtp-secret"  # noqa: S105


@dataclass
class Authority:
    """A throwaway certificate authority that can issue server certificates."""

    key: ec.EllipticCurvePrivateKey
    certificate: x509.Certificate

    @classmethod
    def create(cls, name: str) -> "Authority":
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        now = dt.datetime.now(dt.UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256())
        )
        return cls(key, certificate)

    def issue(self, directory: Path, *, dns_name: str | None, ip: str | None) -> ssl.SSLContext:
        """Return a server context whose certificate names the given host."""
        key = ec.generate_private_key(ec.SECP256R1())
        names: list[x509.GeneralName] = []
        if dns_name:
            names.append(x509.DNSName(dns_name))
        if ip:
            names.append(x509.IPAddress(ipaddress.ip_address(ip)))
        now = dt.datetime.now(dt.UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "smtp test server")]))
            .issuer_name(self.certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .sign(self.key, hashes.SHA256())
        )
        cert_path = directory / f"server-{len(list(directory.iterdir()))}.pem"
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path = cert_path.with_suffix(".key")
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        return context

    def client_context(self) -> ssl.SSLContext:
        """Return a verifying client context that trusts only this authority."""
        context = ssl.create_default_context()
        context.load_verify_locations(cadata=self.certificate.public_bytes(serialization.Encoding.PEM).decode())
        return context


@dataclass
class Received:
    """What the server saw: ordered events, the delivered messages and the logins."""

    events: list[str] = field(default_factory=list[str])
    messages: list[str] = field(default_factory=list[str])
    logins: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])


class _Handler:
    def __init__(self, received: Received, *, stall: bool) -> None:
        self.received = received
        self._stall = stall

    async def handle_DATA(self, server: SMTP, session: Session, envelope: Envelope) -> str:  # noqa: N802
        del server
        self.received.events.append("data:tls" if session.ssl is not None else "data:plain")
        if self._stall:
            await asyncio.sleep(30)
        content = envelope.content
        self.received.messages.append(content.decode() if isinstance(content, bytes) else str(content))
        return "250 OK"


def _authenticator(received: Received, *, accept: bool) -> Callable[..., AuthResult]:
    def authenticate(server: SMTP, session: Session, envelope: Envelope, mechanism: str, data: object) -> AuthResult:
        del server, envelope, mechanism
        received.events.append("auth:tls" if session.ssl is not None else "auth:plain")
        login = bytes(getattr(data, "login", b"")).decode()
        password = bytes(getattr(data, "password", b"")).decode()
        received.logins.append((login, password))
        return AuthResult(success=accept and login == USER and password == PASSWORD)

    return authenticate


def free_port() -> int:
    """Return a TCP port that is free on the loopback address."""
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


@contextmanager
def smtp_server(
    tls_context: ssl.SSLContext | None, *, accept_login: bool = True, stall: bool = False
) -> Generator[tuple[int, Received]]:
    """Run a local SMTP server; without a TLS context it offers no STARTTLS at all."""
    received = Received()
    port = free_port()
    controller = Controller(
        _Handler(received, stall=stall),
        hostname=HOST,
        port=port,
        tls_context=tls_context,
        require_starttls=tls_context is not None,
        auth_required=True,
        auth_require_tls=tls_context is not None,
        authenticator=_authenticator(received, accept=accept_login),
        ready_timeout=10,
    )
    controller.start()
    try:
        yield port, received
    finally:
        controller.stop()
