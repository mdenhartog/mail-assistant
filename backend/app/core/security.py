"""Authorization dependencies shared by all routers.

Every route must declare exactly one of these dependencies so that access control is an
explicit decision; ``tests/test_route_inventory.py`` enforces it.
"""

from collections.abc import Iterable

from fastapi.routing import APIRoute
from starlette.status import HTTP_204_NO_CONTENT

from app.auth.csrf_guard import require_csrf
from app.auth.session import require_session

AUTH_DEPENDENCY_MARKER = "__sdlc_auth__"
AUTH_KINDS = frozenset({"public", "session"})
WRITE_METHODS = frozenset({"POST", "PUT"})
PUBLIC_WRITE_PATHS = frozenset({"/auth/request-code", "/auth/verify-code"})  # the two sign-in routes

# Exact path allow-list of the R1 build (design: API contract); `/api/settings/reset` is R2 and not here.
ROUTE_ALLOW_LIST: frozenset[str] = frozenset(
    {
        "/auth/request-code",
        "/auth/verify-code",
        "/auth/logout",
        "/api/session",
        "/api/settings",
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

    Args:
        routes: Pairs of the full path and the route.

    Returns:
        One message per violation, each naming the path.
    """
    violations: list[str] = []
    for path, route in routes:
        if path not in ROUTE_ALLOW_LIST:
            violations.append(f"{path}: not on the route allow-list")
        kinds = {getattr(dep.call, AUTH_DEPENDENCY_MARKER, None) for dep in route.dependant.dependencies}
        if not kinds & AUTH_KINDS:
            violations.append(f"{path}: declares neither public nor session")
        if route.response_model is None and route.status_code != HTTP_204_NO_CONTENT:
            violations.append(f"{path}: no response_model")
        if (
            (route.methods or set()) & WRITE_METHODS
            and path not in PUBLIC_WRITE_PATHS
            and not {"session", "csrf"} <= kinds
        ):
            violations.append(f"{path}: a write without the session and csrf markers")
    return violations
