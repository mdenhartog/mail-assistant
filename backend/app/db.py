"""Database access for the web role: async engine, TLS, statement timeout and the error that means "not available".

The driver is asyncpg, which takes ``ssl=`` (an ``SSLContext``), not libpq's ``sslmode``: a ``sslmode`` or ``ssl`` in
the URL is dropped and ``Settings.database_ssl`` decides. Nothing here logs or keeps the URL: it holds the password.
"""

import logging
import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

logger = logging.getLogger(__name__)

# The contract version the migrations publish as `settings.contract_version()` (0008: 1, 0012: 2); raise both together.
EXPECTED_CONTRACT_VERSION: Final = 2
CONNECT_TIMEOUT_SECONDS: Final = 10
_MODES: Final = ("require", "verify-ca", "verify-full")
_URL_SSL_KEYS: Final = ("sslmode", "ssl")
# SQLSTATE classes that mean "the database cannot serve this now": connection (08), authentication (28), resources (53)
# and operator intervention (57: includes 57014, a statement cancelled by the timeout).
_UNAVAILABLE_CLASSES: Final = ("08", "28", "53", "57")


class DatabaseUnavailable(Exception):  # noqa: N818  # a state, not a fault of the caller
    """The database cannot serve the request. Carries the error class and the SQLSTATE, never a message or a URL."""

    def __init__(self, error_class: str, sqlstate: str | None) -> None:
        """Build the error from the class name of the cause and its SQLSTATE."""
        super().__init__("database unavailable")
        self.error_class = error_class
        self.sqlstate = sqlstate


def build_ssl_context(mode: str, ca_file: str = "") -> ssl.SSLContext:
    """Build the client TLS context for a database mode (W-8, W-9).

    ``verify-full`` checks the certificate and the host name; ``verify-ca`` only the certificate; ``require`` only
    encrypts. TLS 1.2 is the minimum.

    Args:
        mode: One of ``require``, ``verify-ca`` and ``verify-full``.
        ca_file: A PEM file with the trusted CA; empty uses the system trust store (``SSL_CERT_FILE``).

    Returns:
        The context for the driver's ``ssl`` argument.

    Raises:
        ValueError: The mode is unknown.
    """
    if mode not in _MODES:
        raise ValueError("unknown database ssl mode")
    context = ssl.create_default_context(cafile=ca_file or None)
    context.minimum_version = ssl.TLSVersion.TLSv1_2  # not left to the OpenSSL build: some report "no minimum"
    if mode != "verify-full":
        context.check_hostname = False
    if mode == "require":
        context.verify_mode = ssl.CERT_NONE
    return context


def _driver_arguments(ssl_context: ssl.SSLContext | None, statement_timeout_ms: int) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "timeout": CONNECT_TIMEOUT_SECONDS,
        "server_settings": {"statement_timeout": str(statement_timeout_ms), "application_name": "mail-assistant-api"},
    }
    if ssl_context is not None:
        arguments["ssl"] = ssl_context
    return arguments


def connect_arguments(settings: Settings) -> dict[str, Any]:
    """Build the asyncpg arguments from the settings: the TLS context, the connect and the statement timeout.

    Args:
        settings: The application settings.

    Returns:
        The ``connect_args`` of the engine.
    """
    context = build_ssl_context(settings.database_ssl, settings.database_ca_file)
    return _driver_arguments(context, settings.database_statement_timeout_ms)


def _sqlstate(error: BaseException | None) -> str | None:
    while error is not None:
        for name in ("sqlstate", "pgcode"):
            value = getattr(error, name, None)
            if isinstance(value, str):
                return value
        error = error.__cause__
    return None


def _unavailable(error: BaseException) -> DatabaseUnavailable | None:
    """Return the translation of a driver error, or None when it is a fault of the code and must stay loud."""
    if isinstance(error, OSError | TimeoutError):  # includes TLS failures (ssl.SSLError is an OSError)
        return DatabaseUnavailable(type(error).__name__, None)
    if isinstance(error, DBAPIError):
        sqlstate = _sqlstate(error.orig)
        if error.connection_invalidated or (sqlstate or "").startswith(_UNAVAILABLE_CLASSES):
            cause = error.orig.__cause__ if error.orig is not None else None
            return DatabaseUnavailable(type(cause or error.orig or error).__name__, sqlstate)
    return None


class Database:
    """The engine and session factory of the web role."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Wrap an engine; use ``create`` or ``from_settings``."""
        self._engine = engine
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def create(cls, url: str, *, ssl_context: ssl.SSLContext | None, statement_timeout_ms: int) -> "Database":
        """Create the access to one database.

        Args:
            url: SQLAlchemy URL with the asyncpg driver; a ``sslmode`` or ``ssl`` query value is ignored.
            ssl_context: The TLS context; None only for a local test database without TLS.
            statement_timeout_ms: A statement running longer is cancelled by the server.

        Returns:
            The database access; call ``dispose`` when done.
        """
        parsed = make_url(url).difference_update_query(_URL_SSL_KEYS)
        engine = create_async_engine(
            parsed, connect_args=_driver_arguments(ssl_context, statement_timeout_ms), pool_pre_ping=True
        )
        return cls(engine)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database":
        """Create the access from the settings (always TLS, mode ``database_ssl``).

        Args:
            settings: The application settings.

        Returns:
            The database access; call ``dispose`` when done.
        """
        context = build_ssl_context(settings.database_ssl, settings.database_ca_file)
        return cls.create(
            settings.database_url.get_secret_value(),
            ssl_context=context,
            statement_timeout_ms=settings.database_statement_timeout_ms,
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """Open a session; a database that cannot serve ends in ``DatabaseUnavailable``.

        Yields:
            The session. The caller opens the transaction (``async with session.begin()``).

        Raises:
            DatabaseUnavailable: Connection, TLS, authentication or timeout failure, logged by class and SQLSTATE.
        """
        try:
            async with self._sessions() as session:
                yield session
        except (OSError, TimeoutError, DBAPIError) as error:
            unavailable = _unavailable(error)
            if unavailable is None:
                raise
            logger.error(  # the message and the traceback may carry the URL, so only class and SQLSTATE
                "database.unavailable error_class=%s sqlstate=%s", unavailable.error_class, unavailable.sqlstate
            )
            raise unavailable from None

    async def dispose(self) -> None:
        """Close every pooled connection."""
        await self._engine.dispose()


async def read_contract_version(database: Database) -> int:
    """Ask the database for the contract version it publishes (the web role may execute this one function).

    Args:
        database: The database access.

    Returns:
        The version number.
    """
    async with database.session() as session:
        return (await session.execute(text("SELECT settings.contract_version()"))).scalar_one()
