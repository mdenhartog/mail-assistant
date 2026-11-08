"""Authorization dependencies shared by all routers.

Every route must declare exactly one of these dependencies so that access control is an
explicit decision; ``tests/test_route_inventory.py`` enforces it.
"""

AUTH_DEPENDENCY_MARKER = "__sdlc_auth__"


def public() -> None:
    """Mark a route as intentionally reachable without authentication."""


setattr(public, AUTH_DEPENDENCY_MARKER, True)  # marker read by the route inventory test
