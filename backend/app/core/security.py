"""Authorization dependencies shared by all routers.

Every route must declare exactly one of these dependencies so that access control is an
explicit decision; ``tests/test_route_inventory.py`` enforces it.
"""

from collections.abc import Iterable

from fastapi.routing import APIRoute

from app.errors import ProblemError

AUTH_DEPENDENCY_MARKER = "__sdlc_auth__"
AUTH_KINDS = frozenset({"public", "session"})

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


def session() -> None:
    """Require a session; refuses every request until the session store replaces it (U-web-settings-15).

    Raises:
        ProblemError: Always, with status 401 (fail closed).
    """
    raise ProblemError(401)


setattr(public, AUTH_DEPENDENCY_MARKER, "public")  # marker read by the route inventory test
setattr(session, AUTH_DEPENDENCY_MARKER, "session")


def inventory_violations(routes: Iterable[tuple[str, APIRoute]]) -> list[str]:
    """Name every route that breaks the inventory.

    A route breaks it when its path is not on the allow-list, it declares neither ``public`` nor
    ``session``, or it has no response model.

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
        if route.response_model is None:
            violations.append(f"{path}: no response_model")
    return violations
