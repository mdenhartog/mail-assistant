"""Guards from guardrail-fastapi: every route is on the allow-list and declares ``public`` or ``session``.

Routes are read from the same discovery the app uses to mount them, not from FastAPI internals.
"""

import json

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.core.security import ROUTE_ALLOW_LIST, inventory_violations, public, session
from app.export_openapi import DEFAULT_TARGET
from app.main import discover_routers

R1_PATHS = {
    "/auth/request-code",
    "/auth/verify-code",
    "/auth/logout",
    "/api/session",
    "/api/settings",
    "/api/places",
    "/healthz",
    "/readyz",
}


class _Out(BaseModel):
    ok: bool = True


def _ok() -> _Out:
    return _Out()


def _nothing() -> None:
    return None


def _routes() -> list[tuple[str, APIRoute]]:
    return [
        (mounted.prefix + route.path, route)
        for mounted in discover_routers()
        for route in mounted.router.routes
        if isinstance(route, APIRoute)
    ]


def _routes_of(router: APIRouter) -> list[tuple[str, APIRoute]]:
    return [(route.path, route) for route in router.routes if isinstance(route, APIRoute)]


def test_routers_are_discovered() -> None:
    assert _routes(), "no routers found in app.routers"


def test_given_the_r1_build_when_the_allow_list_is_read_then_it_is_exactly_the_designs_paths() -> None:
    assert set(ROUTE_ALLOW_LIST) == R1_PATHS


def test_the_mounted_routes_pass_the_inventory() -> None:
    assert inventory_violations(_routes()) == []


def test_given_a_route_outside_the_allow_list_when_the_inventory_runs_then_it_fails_naming_the_path() -> None:
    router = APIRouter()
    router.add_api_route("/api/other", _ok, response_model=_Out, dependencies=[Depends(public)])

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert "/api/other" in violations[0]


def test_given_a_route_without_a_marker_when_the_inventory_runs_then_it_fails_naming_the_path() -> None:
    router = APIRouter()
    router.add_api_route("/api/settings", _ok, response_model=_Out)

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert "/api/settings" in violations[0]


def test_given_the_r2_reset_route_when_the_inventory_runs_then_it_fails_naming_the_path() -> None:
    router = APIRouter()
    router.add_api_route(
        "/api/settings/reset", _ok, response_model=_Out, methods=["POST"], dependencies=[Depends(session)]
    )

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert "/api/settings/reset" in violations[0]


def test_given_allowed_routes_with_public_or_session_when_the_inventory_runs_then_it_passes() -> None:
    router = APIRouter()
    router.add_api_route("/api/settings", _ok, response_model=_Out, dependencies=[Depends(session)])
    router.add_api_route("/auth/request-code", _ok, response_model=_Out, dependencies=[Depends(public)])

    assert inventory_violations(_routes_of(router)) == []


def test_given_a_route_without_a_response_model_when_the_inventory_runs_then_it_fails() -> None:
    router = APIRouter()
    router.add_api_route("/api/settings", _nothing, dependencies=[Depends(session)])

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert "/api/settings" in violations[0]


def test_given_the_checked_in_document_when_read_then_every_path_is_on_the_allow_list() -> None:
    document = json.loads(DEFAULT_TARGET.read_text(encoding="utf-8"))

    assert set(document["paths"]) <= set(ROUTE_ALLOW_LIST)
