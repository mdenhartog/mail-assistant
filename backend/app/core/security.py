"""Authorization dependencies shared by all routers.

Every route must declare exactly one of these dependencies so that access control is an
explicit decision; ``tests/test_route_inventory.py`` enforces it.
"""

from collections.abc import Iterable, Iterator

from fastapi.routing import APIRoute
from starlette.status import HTTP_204_NO_CONTENT

from app.auth.csrf_guard import require_csrf
from app.auth.session import require_session

AUTH_DEPENDENCY_MARKER = "__sdlc_auth__"
AUTH_KINDS = frozenset({"public", "session"})
LIMIT_KIND = "limit"  # the marker of ``limit(bucket)`` dependencies, read in order by the inventory
PROBE_PATHS = frozenset({"/healthz", "/readyz"})  # the probes are not limited
WRITE_METHODS = frozenset({"POST", "PUT"})
PUBLIC_WRITE_PATHS = frozenset({"/auth/request-code", "/auth/verify-code"})  # the two sign-in routes

# Exact path allow-list (design: API contract); `/api/settings/reset` joined it with R2 (U-web-settings-45).
ROUTE_ALLOW_LIST: frozenset[str] = frozenset(
    {
        "/auth/request-code",
        "/auth/verify-code",
        "/auth/logout",
        "/api/session",
        "/api/settings",
        "/api/settings/reset",
        "/api/places",
        "/healthz",
        "/readyz",
    }
)


def public() -> None:
    """Mark a route as intentionally reachable without authentication."""


session = require_session  # the dependency routes declare: a live session or 401, fail closed


csrf = require_csrf  # the dependency every POST and PUT declares next to ``session``

setattr(csrf, AUTH_DEPENDENCY_MARKER, "csrf")
setattr(public, AUTH_DEPENDENCY_MARKER, "public")  # marker read by the route inventory test
setattr(session, AUTH_DEPENDENCY_MARKER, "session")


def inventory_violations(routes: Iterable[tuple[str, APIRoute]]) -> list[str]:
    """Name every route that breaks the inventory.

    A route breaks it when its path is not on the allow-list, it declares neither ``public`` nor
    ``session``, it has no response model (a 204 has no body and is exempt), or it is a ``POST`` or ``PUT``
    other than the two public sign-in routes without both the ``session`` and ``csrf`` markers.
    Every route but the probes must also carry a ``limit`` marker, and before the ``session`` marker when it has one,
    so a flood is counted before any session lookup.

    Args:
        routes: Pairs of the full path and the route.

    Returns:
        One message per violation, each naming the path.
    """
    violations: list[str] = []
    for path, route in routes:
        violations.extend(_route_violations(path, route))
    return violations


def _route_violations(path: str, route: APIRoute) -> Iterator[str]:
    order = [getattr(dep.call, AUTH_DEPENDENCY_MARKER, None) for dep in route.dependant.dependencies]
    kinds = set(order)
    if path not in ROUTE_ALLOW_LIST:
        yield f"{path}: not on the route allow-list"
    if not kinds & AUTH_KINDS:
        yield f"{path}: declares neither public nor session"
    if route.response_model is None and route.status_code != HTTP_204_NO_CONTENT:
        yield f"{path}: no response_model"
    yield from _limit_violations(path, order)
    is_write = bool((route.methods or set()) & WRITE_METHODS)
    if is_write and path not in PUBLIC_WRITE_PATHS and not {"session", "csrf"} <= kinds:
        yield f"{path}: a write without the session and csrf markers"


def _limit_violations(path: str, order: list[str | None]) -> Iterator[str]:
    if path in PROBE_PATHS or not set(order) & AUTH_KINDS:
        return
    if LIMIT_KIND not in order:
        yield f"{path}: no limit marker"
    elif "session" in order and order.index(LIMIT_KIND) > order.index("session"):
        yield f"{path}: the limit marker comes after the session marker"
