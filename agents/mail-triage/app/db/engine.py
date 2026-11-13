"""Database connections of the agent and the migrate job: TLS decided by the settings, never by the URL (SEC-10).

The driver is asyncpg, which takes ``ssl=`` (an ``SSLContext``, or ``False`` for no TLS), not libpq's ``sslmode``. A
``ssl`` value inside the connection URL is dropped: the URL is a secret that an operator can get wrong, the settings are
checked at start-up (production refuses anything weaker than ``verify-full``). Nothing here logs or keeps the URL.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

SSL_MODES: Final = ("disable", "require", "verify-ca", "verify-full")


@dataclass(frozen=True)
class DatabaseTls:
    """How to reach the database: the mode and the PEM file of the trusted CA (empty: the system trust store)."""

    mode: str
    ca_file: str = ""


def ssl_argument(mode: str, ca_file: str = "") -> ssl.SSLContext | bool:
    """Build the driver's ``ssl`` argument for a mode.

    ``verify-full`` checks the certificate and the host name; ``verify-ca`` only the certificate; ``require`` only
    encrypts; ``disable`` is no TLS at all (development only: production refuses it at start-up). TLS 1.2 is the
    minimum.

    Args:
        mode: One of ``SSL_MODES``.
        ca_file: A PEM file with the trusted CA; empty uses the system trust store.

    Returns:
        ``False`` for ``disable``, else the context.

    Raises:
        ValueError: The mode is unknown.
    """
    if mode not in SSL_MODES:
        raise ValueError("unknown database ssl mode")
    if mode == "disable":
        return False
    context = ssl.create_default_context(cafile=ca_file or None)
    context.minimum_version = ssl.TLSVersion.TLSv1_2  # not left to the OpenSSL build
    if mode != "verify-full":
        context.check_hostname = False
    if mode == "require":
        context.verify_mode = ssl.CERT_NONE
    return context


def connect_args(tls: DatabaseTls) -> dict[str, Any]:
    """The ``connect_args`` of an asyncpg engine (and the keyword arguments of ``asyncpg.connect``)."""
    return {"ssl": ssl_argument(tls.mode, tls.ca_file)}


def make_engine(url: str, tls: DatabaseTls) -> AsyncEngine:
    """The one database engine; bound parameters (a stored time zone, a typed answer) never reach an error or a log."""
    return create_async_engine(url, hide_parameters=True, connect_args=connect_args(tls))
