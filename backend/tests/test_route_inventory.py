"""Guards from guardrail-fastapi: every route declares an auth dependency and a response model.

Routes are read from the same discovery the app uses to mount them, not from FastAPI internals.
"""

from fastapi.routing import APIRoute

from app.core.security import AUTH_DEPENDENCY_MARKER
from app.main import discover_routers

PROBES = {"/healthz", "/readyz"}


def _routes() -> list[tuple[str, APIRoute]]:
    return [
        (mounted.prefix + route.path, route)
        for mounted in discover_routers()
        for route in mounted.router.routes
        if isinstance(route, APIRoute)
    ]


def test_routers_are_discovered() -> None:
    assert _routes(), "no routers found in app.routers"


def test_every_route_declares_an_auth_dependency() -> None:
    missing = [
        path
        for path, route in _routes()
        if not any(getattr(dep.call, AUTH_DEPENDENCY_MARKER, False) for dep in route.dependant.dependencies)
    ]

    assert missing == [], f"routes without public/role dependency: {missing}"


def test_business_routes_live_under_api_prefix() -> None:
    outside = [path for path, _ in _routes() if path not in PROBES and not path.startswith("/api/")]

    assert outside == [], f"routes outside /api: {outside}"


def test_every_route_declares_a_response_model() -> None:
    missing = [path for path, route in _routes() if route.response_model is None]

    assert missing == [], f"routes without response_model: {missing}"
