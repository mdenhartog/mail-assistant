"""Verify-code endpoint logic (U-web-settings-18, ADR-0036)."""

from fastapi import FastAPI, Response

from app.auth.login_requests import LoginRequests
from app.auth.session import SessionStore
from app.security_events import SecurityEvents


def clear_login_cookie() -> str:
    """Return the ``Set-Cookie`` value that ends the login cookie in the browser."""
    raise NotImplementedError


class VerifyCode:
    """Checks a posted code and signs the visitor in."""

    async def verify(self, raw_body: bytes, cookie: str | None, client: str, request_id: str) -> Response:
        """Answer a code check."""
        raise NotImplementedError


def attach_verify_code(app: FastAPI, logins: LoginRequests, sessions: SessionStore, events: SecurityEvents) -> None:
    """Give the app the use case behind the verify-code route."""
    raise NotImplementedError
