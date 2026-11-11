"""Request-code endpoint logic (U-web-settings-17)."""

from datetime import datetime
from typing import Final

from fastapi import FastAPI

from app.auth.code_hash import hash_code
from app.auth.login_requests import LoginRequests
from app.security_events import SecurityEvents

LOGIN_COOKIE_NAME: Final = "__Host-login"
_HASH = hash_code  # skeleton


class RecentRequests:
    """In-process record of code requests for usernames that are not the configured one."""

    def __init__(self, *, max_keys: int) -> None:
        """Keep at most ``max_keys`` usernames."""
        raise NotImplementedError

    def record(self, key: str, now: datetime) -> None:
        """Remember a request."""
        raise NotImplementedError

    def times(self, key: str, now: datetime) -> list[datetime]:
        """Return the requests of the last hour."""
        raise NotImplementedError


def attach_request_code(app: FastAPI, store: LoginRequests, events: SecurityEvents) -> None:
    """Give the app the stores the request-code route needs."""
    raise NotImplementedError
