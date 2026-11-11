"""Database access for the web role (skeleton; the real module follows the tests)."""

import ssl
from contextlib import AbstractAsyncContextManager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings

EXPECTED_CONTRACT_VERSION = 1


class DatabaseUnavailable(Exception):  # noqa: N818
    """The database cannot serve the request."""

    error_class: str
    sqlstate: str | None


def build_ssl_context(mode: str, ca_file: str = "") -> ssl.SSLContext:
    """Build the TLS context for a mode."""
    raise NotImplementedError


def connect_arguments(settings: Settings) -> dict[str, Any]:
    """Build the driver arguments."""
    raise NotImplementedError


class Database:
    """Engine and session factory."""

    @classmethod
    def create(cls, url: str, *, ssl_context: ssl.SSLContext | None, statement_timeout_ms: int) -> "Database":
        """Create from an URL."""
        raise NotImplementedError

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database":
        """Create from settings."""
        raise NotImplementedError

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Open a session."""
        raise NotImplementedError

    async def dispose(self) -> None:
        """Close the pool."""
        raise NotImplementedError
