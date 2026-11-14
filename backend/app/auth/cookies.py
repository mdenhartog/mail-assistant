"""The ``__Host-`` cookies of the web login: one builder for every one of them (U-web-settings-60, AC-7).

A ``__Host-`` cookie is Secure, has Path=/ and no Domain; ours are also HttpOnly and SameSite=Lax. Both the session
cookie and the login request cookie, set or cleared, are built here and nowhere else.
"""

from http.cookies import SimpleCookie
from typing import Final

from app.config import LOGIN_COOKIE_MAX_AGE_SECONDS, SESSION_COOKIE_MAX_AGE_SECONDS

COOKIE_NAME: Final = "__Host-session"
LOGIN_COOKIE_NAME: Final = "__Host-login"
_EXPIRED: Final = "Thu, 01 Jan 1970 00:00:00 GMT"


def _host_cookie(name: str, value: str, max_age: int) -> SimpleCookie:
    jar: SimpleCookie = SimpleCookie()
    jar[name] = value
    morsel = jar[name]
    morsel["httponly"] = True
    morsel["secure"] = True
    morsel["samesite"] = "Lax"
    morsel["path"] = "/"
    morsel["max-age"] = str(max_age)
    return jar


def _set(name: str, value: str, max_age: int) -> str:
    return _host_cookie(name, value, max_age)[name].OutputString()


def _clear(name: str) -> str:
    jar = _host_cookie(name, "", 0)
    jar[name]["expires"] = _EXPIRED
    return jar[name].OutputString()


def session_cookie(value: str) -> str:
    """Build the ``Set-Cookie`` value of the session cookie.

    Args:
        value: The session id.

    Returns:
        The header value.
    """
    return _set(COOKIE_NAME, value, SESSION_COOKIE_MAX_AGE_SECONDS)


def clear_session_cookie() -> str:
    """Build the ``Set-Cookie`` value that ends the session cookie in the browser (same attributes, expired now).

    Returns:
        The header value.
    """
    return _clear(COOKIE_NAME)


def login_cookie(value: str) -> str:
    """Build the ``Set-Cookie`` value of the login request cookie.

    Args:
        value: The login request id.

    Returns:
        The header value.
    """
    return _set(LOGIN_COOKIE_NAME, value, LOGIN_COOKIE_MAX_AGE_SECONDS)


def clear_login_cookie() -> str:
    """Build the ``Set-Cookie`` value that ends the login cookie in the browser (same attributes, expired now).

    Returns:
        The header value.
    """
    return _clear(LOGIN_COOKIE_NAME)
