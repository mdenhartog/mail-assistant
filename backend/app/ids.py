import secrets
from typing import Protocol

_ID_BYTES = 32


class IdSource(Protocol):
    """Source of random tokens and ids; the only place the app draws randomness for ids."""

    def token(self, nbytes: int) -> str:
        """Return a URL-safe token made from nbytes random bytes."""
        ...

    def session_id(self) -> str:
        """Return a new session id."""
        ...

    def login_request_id(self) -> str:
        """Return a new login request id."""
        ...

    def request_id(self) -> str:
        """Return a new request id."""
        ...


class SecretsIdSource:
    """Production id source."""

    def token(self, nbytes: int) -> str:
        """Return a URL-safe token made from nbytes random bytes."""
        return secrets.token_urlsafe(nbytes)

    def session_id(self) -> str:
        """Return a new session id (43 URL-safe characters)."""
        return self.token(_ID_BYTES)

    def login_request_id(self) -> str:
        """Return a new login request id (43 URL-safe characters)."""
        return self.token(_ID_BYTES)

    def request_id(self) -> str:
        """Return a new request id (43 URL-safe characters)."""
        return self.token(_ID_BYTES)
