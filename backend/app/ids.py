from typing import Protocol


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
        raise NotImplementedError

    def session_id(self) -> str:
        """Return a new session id."""
        raise NotImplementedError

    def login_request_id(self) -> str:
        """Return a new login request id."""
        raise NotImplementedError

    def request_id(self) -> str:
        """Return a new request id."""
        raise NotImplementedError
