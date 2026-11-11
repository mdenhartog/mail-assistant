"""Authorization dependencies shared by all routers.

Every route must declare exactly one of these dependencies so that access control is an
explicit decision; ``tests/test_route_inventory.py`` enforces it.
"""

from collections.abc import Iterable

from fastapi.routing import APIRoute

AUTH_DEPENDENCY_MARKER = "__sdlc_auth__"

ROUTE_ALLOW_LIST: frozenset[str] = frozenset()


def public() -> None:
    """Mark a route as intentionally reachable without authentication."""


setattr(public, AUTH_DEPENDENCY_MARKER, True)  # marker read by the route inventory test


def session() -> None:
    """Require a session."""
    raise NotImplementedError


def inventory_violations(routes: Iterable[tuple[str, APIRoute]]) -> list[str]:
    """Name every route that breaks the inventory."""
    raise NotImplementedError
