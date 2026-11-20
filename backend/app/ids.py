import base64
import secrets
import uuid
from typing import Protocol

_ID_BYTES = 32
_UUID_BYTES = 16


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

    def category_id(self) -> uuid.UUID:
        """Return the stable id of a new category."""
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

    def category_id(self) -> uuid.UUID:
        """Return the id of a new category (a random version 4 UUID made from 16 random bytes of the token source)."""
        return uuid.UUID(bytes=base64.urlsafe_b64decode(self.token(_UUID_BYTES) + "=="), version=4)
