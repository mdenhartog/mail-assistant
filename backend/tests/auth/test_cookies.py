"""U-web-settings-60: every ``__Host-`` cookie is built and cleared by one module with the same attributes (AC-7)."""

from collections.abc import Callable
from http.cookies import Morsel, SimpleCookie

import pytest

from app.auth import cookies
from app.config import LOGIN_COOKIE_MAX_AGE_SECONDS, SESSION_COOKIE_MAX_AGE_SECONDS

VALUE = "opaque-value"
EXPIRED = "Thu, 01 Jan 1970 00:00:00 GMT"

SET_CASES: list[tuple[str, Callable[[str], str], str, int]] = [
    ("session", cookies.session_cookie, "__Host-session", SESSION_COOKIE_MAX_AGE_SECONDS),
    ("login", cookies.login_cookie, "__Host-login", LOGIN_COOKIE_MAX_AGE_SECONDS),
]
CLEAR_CASES: list[tuple[str, Callable[[], str], str]] = [
    ("session", cookies.clear_session_cookie, "__Host-session"),
    ("login", cookies.clear_login_cookie, "__Host-login"),
]


def _morsel(header: str, name: str) -> Morsel[str]:
    jar: SimpleCookie = SimpleCookie()
    jar.load(header)
    assert list(jar) == [name]
    return jar[name]


def _assert_host_rules(morsel: Morsel[str], name: str) -> None:
    assert name.startswith("__Host-")
    assert morsel["secure"] is True
    assert morsel["httponly"] is True
    assert morsel["samesite"] == "Lax"
    assert morsel["path"] == "/"
    assert morsel["domain"] == ""


@pytest.mark.parametrize(("label", "build", "name", "max_age"), SET_CASES, ids=[c[0] for c in SET_CASES])
def test_given_a_cookie_when_set_then_it_keeps_the_host_rules_and_its_max_age(
    label: str, build: Callable[[str], str], name: str, max_age: int
) -> None:
    morsel = _morsel(build(VALUE), name)

    _assert_host_rules(morsel, name)
    assert morsel.value == VALUE
    assert morsel["max-age"] == str(max_age)


@pytest.mark.parametrize(("label", "build", "name"), CLEAR_CASES, ids=[c[0] for c in CLEAR_CASES])
def test_given_a_cookie_when_cleared_then_it_keeps_the_host_rules_and_ends_now(
    label: str, build: Callable[[], str], name: str
) -> None:
    morsel = _morsel(build(), name)

    _assert_host_rules(morsel, name)
    assert morsel.value == ""
    assert morsel["max-age"] == "0"
    assert morsel["expires"] == EXPIRED


def test_given_the_cookie_module_when_listing_its_names_then_they_are_the_two_host_cookies() -> None:
    assert cookies.COOKIE_NAME == "__Host-session"
    assert cookies.LOGIN_COOKIE_NAME == "__Host-login"
