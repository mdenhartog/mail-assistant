"""The ``__Host-`` cookies of the web login: one builder for every one of them (U-web-settings-60)."""

from typing import Final

COOKIE_NAME: Final = "__Host-session"
LOGIN_COOKIE_NAME: Final = "__Host-login"


def session_cookie(value: str) -> str:
    """Stub."""
    raise NotImplementedError


def clear_session_cookie() -> str:
    """Stub."""
    raise NotImplementedError


def login_cookie(value: str) -> str:
    """Stub."""
    raise NotImplementedError


def clear_login_cookie() -> str:
    """Stub."""
    raise NotImplementedError
