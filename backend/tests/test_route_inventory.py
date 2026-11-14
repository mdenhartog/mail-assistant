"""Guards from guardrail-fastapi: every route is on the allow-list and declares ``public`` or ``session``.

Routes are read from the same discovery the app uses to mount them, not from FastAPI internals.
"""

import json

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.core.security import ROUTE_ALLOW_LIST, csrf, inventory_violations, public, session
from app.export_openapi import DEFAULT_TARGET
from app.limit_guard import limit
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


SIGN_IN_PATHS = {"/auth/request-code", "/auth/verify-code"}


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


def test_given_the_mounted_routes_when_read_then_the_paths_equal_the_allow_list() -> None:
    mounted = {path for path, _ in _routes()}

    assert mounted == set(ROUTE_ALLOW_LIST)


def test_the_mounted_routes_pass_the_inventory() -> None:
    assert inventory_violations(_routes()) == []


def test_given_a_route_outside_the_allow_list_when_the_inventory_runs_then_it_fails_naming_the_path() -> None:
    router = APIRouter()
    router.add_api_route(
        "/api/other", _ok, response_model=_Out, dependencies=[Depends(limit("signin")), Depends(public)]
    )

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
        "/api/settings/reset",
        _ok,
        response_model=_Out,
        methods=["POST"],
        dependencies=[Depends(limit("api")), Depends(session)],
    )

    violations = inventory_violations(_routes_of(router))

    assert any("/api/settings/reset" in v and "allow-list" in v for v in violations)


def test_given_allowed_routes_with_public_or_session_when_the_inventory_runs_then_it_passes() -> None:
    router = APIRouter()
    router.add_api_route(
        "/api/settings", _ok, response_model=_Out, dependencies=[Depends(limit("api")), Depends(session)]
    )
    router.add_api_route(
        "/auth/request-code", _ok, response_model=_Out, dependencies=[Depends(limit("signin")), Depends(public)]
    )

    assert inventory_violations(_routes_of(router)) == []


def test_given_a_route_without_a_response_model_when_the_inventory_runs_then_it_fails() -> None:
    router = APIRouter()
    router.add_api_route("/api/settings", _nothing, dependencies=[Depends(limit("api")), Depends(session)])

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert "/api/settings" in violations[0]


def test_given_the_checked_in_document_when_read_then_every_path_is_on_the_allow_list() -> None:
    document = json.loads(DEFAULT_TARGET.read_text(encoding="utf-8"))

    assert set(document["paths"]) <= set(ROUTE_ALLOW_LIST)


def test_given_a_post_or_put_without_the_csrf_marker_when_the_inventory_runs_then_it_fails_naming_the_path() -> None:
    router = APIRouter()
    router.add_api_route(
        "/auth/logout",
        _ok,
        response_model=_Out,
        methods=["POST"],
        dependencies=[Depends(limit("api")), Depends(session)],
    )
    router.add_api_route(
        "/api/settings",
        _ok,
        response_model=_Out,
        methods=["PUT"],
        dependencies=[Depends(limit("api")), Depends(session)],
    )

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 2
    assert any("/auth/logout" in v and "csrf" in v for v in violations)
    assert any("/api/settings" in v and "csrf" in v for v in violations)


def test_given_a_post_or_put_with_session_and_csrf_when_the_inventory_runs_then_it_passes() -> None:
    router = APIRouter()
    dependencies = [Depends(limit("api")), Depends(session), Depends(csrf)]
    router.add_api_route("/auth/logout", _ok, response_model=_Out, methods=["POST"], dependencies=dependencies)
    router.add_api_route("/api/settings", _ok, response_model=_Out, methods=["PUT"], dependencies=dependencies)

    assert inventory_violations(_routes_of(router)) == []


def test_given_the_two_public_sign_in_posts_when_the_inventory_runs_then_they_need_no_csrf_marker() -> None:
    router = APIRouter()
    for path in ("/auth/request-code", "/auth/verify-code"):
        router.add_api_route(
            path, _ok, response_model=_Out, methods=["POST"], dependencies=[Depends(limit("signin")), Depends(public)]
        )

    assert inventory_violations(_routes_of(router)) == []


def test_given_a_public_post_outside_the_two_sign_in_routes_when_the_inventory_runs_then_it_fails() -> None:
    router = APIRouter()
    router.add_api_route(
        "/api/settings",
        _ok,
        response_model=_Out,
        methods=["POST"],
        dependencies=[Depends(limit("signin")), Depends(public)],
    )

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert "/api/settings" in violations[0]


def test_given_a_get_route_when_the_inventory_runs_then_it_needs_no_csrf_marker() -> None:
    router = APIRouter()
    router.add_api_route(
        "/api/session", _ok, response_model=_Out, dependencies=[Depends(limit("api")), Depends(session)]
    )

    assert inventory_violations(_routes_of(router)) == []


def test_given_a_204_route_without_a_response_model_when_the_inventory_runs_then_it_passes() -> None:
    router = APIRouter()
    router.add_api_route(
        "/auth/logout",
        _nothing,
        status_code=204,
        methods=["POST"],
        dependencies=[Depends(limit("api")), Depends(session), Depends(csrf)],
    )

    assert inventory_violations(_routes_of(router)) == []


def test_given_the_mounted_write_routes_when_read_then_each_has_the_session_and_csrf_markers() -> None:
    writes = [(p, r) for p, r in _routes() if (r.methods or set()) & {"POST", "PUT"} and p not in SIGN_IN_PATHS]

    assert sorted(p for p, _ in writes) == ["/api/settings", "/auth/logout"]
    assert inventory_violations(writes) == []


def test_given_a_route_breaking_every_rule_when_the_inventory_runs_then_each_rule_reports_once() -> None:
    router = APIRouter()
    router.add_api_route("/api/other", _nothing, methods=["POST"])

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 4
    assert all(v.startswith("/api/other:") for v in violations)


# ---- U-web-settings-51, criterion 4: a limit marker before the session marker ----

PROBE_PATHS = {"/healthz", "/readyz"}


def test_given_the_mounted_non_probe_routes_when_read_then_each_has_a_limit_before_the_session() -> None:
    routes = [(p, r) for p, r in _routes() if p not in PROBE_PATHS]

    assert routes
    assert inventory_violations(routes) == []
    for path, route in routes:
        order = [getattr(dep.call, "__sdlc_auth__", None) for dep in route.dependant.dependencies]
        assert "limit" in order, path
        if "session" in order:
            assert order.index("limit") < order.index("session"), path


def test_given_a_session_route_with_the_limit_after_the_session_when_the_inventory_runs_then_it_fails_naming_it() -> (
    None
):
    router = APIRouter()
    router.add_api_route(
        "/api/places", _ok, response_model=_Out, dependencies=[Depends(session), Depends(limit("api"))]
    )

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert violations[0].startswith("/api/places:")
    assert "limit" in violations[0]


def test_given_a_session_route_without_a_limit_when_the_inventory_runs_then_it_fails_naming_it() -> None:
    router = APIRouter()
    router.add_api_route("/api/session", _ok, response_model=_Out, dependencies=[Depends(session)])

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert violations[0].startswith("/api/session:")


def test_given_a_session_route_with_the_limit_first_when_the_inventory_runs_then_it_passes() -> None:
    router = APIRouter()
    router.add_api_route(
        "/api/places", _ok, response_model=_Out, dependencies=[Depends(limit("api")), Depends(session)]
    )

    assert inventory_violations(_routes_of(router)) == []


def test_given_a_public_route_without_a_limit_when_the_inventory_runs_then_it_fails_naming_it() -> None:
    router = APIRouter()
    router.add_api_route(
        "/auth/request-code", _ok, response_model=_Out, methods=["POST"], dependencies=[Depends(public)]
    )

    violations = inventory_violations(_routes_of(router))

    assert len(violations) == 1
    assert violations[0].startswith("/auth/request-code:")


def test_given_a_probe_without_a_limit_when_the_inventory_runs_then_it_passes() -> None:
    router = APIRouter()
    router.add_api_route("/healthz", _ok, response_model=_Out, dependencies=[Depends(public)])

    assert inventory_violations(_routes_of(router)) == []
