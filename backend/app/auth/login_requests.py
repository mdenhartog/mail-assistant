"""Login request store (U-web-settings-16): persistence of the e-mailed sign-in code in ``web_auth.login_request``."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.db import Database
from app.ids import IdSource


@dataclass(frozen=True)
class LoginRequest:
    """A stored login request: its id (the ``__Host-login`` cookie value) and its times."""

    id: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class Ok:
    """The code was right; the request is now dead."""


@dataclass(frozen=True)
class Wrong:
    """The code was wrong; ``attempts_left`` more may be tried."""

    attempts_left: int


@dataclass(frozen=True)
class Dead:
    """The request is unknown, replaced, used, expired or out of attempts."""


Verdict = Ok | Wrong | Dead


class LoginRequestCapReached(Exception):  # noqa: N818  # a state, not a fault
    """Too many open login requests; nothing was written."""


class LoginRequests:
    """Store of login requests for the web role."""

    def __init__(
        self, database: Database, ids: IdSource, *, hash_key: bytes, ttl: timedelta, max_attempts: int
    ) -> None:
        """Build the store."""
        raise NotImplementedError

    async def create(self, username_key: str, code: str, now: datetime, cap: int) -> LoginRequest:
        """Create a request."""
        raise NotImplementedError

    async def check(self, request_id: str | None, code: str, now: datetime) -> Verdict:
        """Check a code."""
        raise NotImplementedError

    async def mark_sent(self, request_id: str, now: datetime) -> None:
        """Mark a request as sent."""
        raise NotImplementedError

    async def last_requested_at(self, username_key: str) -> datetime | None:
        """Return the newest creation time."""
        raise NotImplementedError

    async def sent_in_last_hour(self, username_key: str, now: datetime) -> int:
        """Count the sent codes of the last hour."""
        raise NotImplementedError
