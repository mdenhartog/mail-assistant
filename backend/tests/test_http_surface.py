"""HTTP surface: error model, headers, request id and the limit seam (U-web-settings-05)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response

from app.config import Settings
from app.core.security import AUTH_DEPENDENCY_MARKER, public, session
from app.errors import PROBLEM_MEDIA_TYPE, ProblemError, RateLimited
from app.limit_guard import limit
from app.main import discover_routers
from app.routers import settings as settings_router
from tests.fakes import make_app, make_settings

SECURITY_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"
ISOLATION_HEADERS = {
    "content-security-policy": API_CSP,
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}


class CanaryFailureError(Exception):
    """Carries a secret in its message; only the class name may reach the log."""


def _add_routes(app: FastAPI) -> None:
    @app.get("/t/boom", dependencies=[Depends(public)])
    async def boom() -> None:
        msg = "canary-user must never leave the server"
        raise CanaryFailureError(msg)

    @app.get("/t/problem/{status}", dependencies=[Depends(public)])
    async def problem(status: int) -> None:
        raise ProblemError(status)

    @app.get("/t/html", dependencies=[Depends(public)], response_class=HTMLResponse)
    async def html() -> str:
        return "<p>hello</p>"

    @app.get("/t/session", dependencies=[Depends(session)])
    async def needs_session() -> None:
        return None

    @app.get("/t/limited", dependencies=[Depends(public), Depends(limit("test-bucket"))])
    async def limited() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/t/post-only", dependencies=[Depends(public)])
    async def post_only() -> None:
        return None


@pytest.fixture
def surface_app() -> FastAPI:
    app = make_app()
    _add_routes(app)
    return app


@pytest.fixture
async def surface(surface_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=surface_app), base_url="http://test")


def _assert_generic_problem(response: Response, status: int) -> None:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert set(body) == {"type", "title", "status"}
    assert body["status"] == status
    assert body["type"] == "about:blank"
    assert isinstance(body["title"], str)
    assert body["title"]


# 1
async def test_given_unhandled_exception_with_canary_when_answered_then_generic_500_and_class_name_only_in_log(
    surface: AsyncClient, canary_log_records: list[logging.LogRecord]
) -> None:
    response = await surface.get("/t/boom")

    _assert_generic_problem(response, 500)
    assert "CanaryFailureError" not in response.text
    assert "canary-user" not in response.text
    assert "Traceback" not in response.text
    errors = [r for r in canary_log_records if r.levelno >= logging.ERROR]
    assert any("CanaryFailureError" in r.getMessage() for r in errors)
    assert all("canary-user" not in r.getMessage() and r.exc_info is None for r in errors)


# 2
async def test_given_unknown_path_when_requested_then_404_generic_problem(surface: AsyncClient) -> None:
    response = await surface.get("/does-not-exist")

    _assert_generic_problem(response, 404)
    assert "does-not-exist" not in response.text
    assert "Not Found" not in response.text


async def test_given_wrong_method_when_requested_then_405_generic_problem(surface: AsyncClient) -> None:
    response = await surface.get("/t/post-only")

    _assert_generic_problem(response, 405)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 413, 415, 500])
async def test_given_a_refusal_when_raised_then_the_generic_problem_of_that_status(
    surface: AsyncClient, status: int
) -> None:
    response = await surface.get(f"/t/problem/{status}")

    _assert_generic_problem(response, status)


async def test_given_session_dependency_without_session_when_called_then_401_problem(surface: AsyncClient) -> None:
    response = await surface.get("/t/session")

    _assert_generic_problem(response, 401)


# 3
@pytest.mark.parametrize(
    ("path", "status"),
    [("/healthz", 200), ("/t/problem/400", 400), ("/t/problem/401", 401), ("/nowhere", 404), ("/t/boom", 500)],
)
async def test_given_any_response_when_inspected_then_security_headers_are_present(
    surface: AsyncClient, path: str, status: int
) -> None:
    response = await surface.get(path)

    assert response.status_code == status
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value, name


async def test_given_429_when_inspected_then_security_headers_are_present(surface_app: FastAPI) -> None:
    surface_app.state.limit_guard = _RaisingGuard(30)
    async with AsyncClient(transport=ASGITransport(app=surface_app), base_url="http://test") as client:
        response = await client.get("/t/limited")

    assert response.status_code == 429
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value, name


# 4 (U-web-settings-59: one policy for every response, html or not)
@pytest.mark.parametrize("path", ["/t/html", "/healthz"])
async def test_given_any_content_type_when_inspected_then_the_csp_is_the_one_api_policy(
    surface: AsyncClient, path: str
) -> None:
    response = await surface.get(path)

    assert response.headers["content-security-policy"] == API_CSP


@pytest.mark.parametrize(
    ("path", "status"),
    [("/healthz", 200), ("/t/problem/400", 400), ("/t/problem/401", 401), ("/nowhere", 404), ("/t/boom", 500)],
)
async def test_given_any_response_when_inspected_then_csp_coop_and_corp_are_present(
    surface: AsyncClient, path: str, status: int
) -> None:
    response = await surface.get(path)

    assert response.status_code == status
    for name, value in ISOLATION_HEADERS.items():
        assert response.headers[name] == value, name


async def test_given_429_when_inspected_then_csp_coop_and_corp_are_present(surface_app: FastAPI) -> None:
    surface_app.state.limit_guard = _RaisingGuard(30)
    async with AsyncClient(transport=ASGITransport(app=surface_app), base_url="http://test") as client:
        response = await client.get("/t/limited")

    assert response.status_code == 429
    for name, value in ISOLATION_HEADERS.items():
        assert response.headers[name] == value, name


@pytest.mark.parametrize("path", ["/docs", "/docs/oauth2-redirect"])
async def test_given_development_when_the_docs_are_served_then_they_have_their_own_csp(path: str) -> None:
    app = make_app(make_settings(environment="development"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert csp != API_CSP
    assert csp.startswith("default-src 'none'")
    assert "frame-ancestors 'none'" in csp
    assert "script-src 'self' https://cdn.jsdelivr.net" in csp
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"


async def test_given_development_when_the_openapi_document_is_served_then_it_has_the_api_policy() -> None:
    app = make_app(make_settings(environment="development"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["content-security-policy"] == API_CSP


# Criterion 1 of U-web-settings-59
def test_given_no_environment_variable_when_settings_load_then_production_rules_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_ENVIRONMENT", raising=False)

    settings = Settings()

    assert settings.environment == "production"
    assert settings.docs_enabled is False


@pytest.mark.parametrize("value", ["development", "test"])
def test_given_an_explicit_environment_when_settings_load_then_it_is_kept(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", value)

    assert Settings().environment == value


# U-web-settings-59: session is declared once on PUT /api/settings
def test_given_the_settings_write_route_when_inspected_then_session_is_declared_once_after_the_limit() -> None:
    route = next(
        r
        for m in discover_routers()
        for r in m.router.routes
        if isinstance(r, APIRoute) and r.path == "/settings" and "PUT" in (r.methods or set())
    )
    calls = [dep.call for dep in route.dependant.dependencies]

    assert calls.count(session) == 1
    assert [getattr(c, AUTH_DEPENDENCY_MARKER, None) for c in calls].index("limit") < calls.index(session)


def test_given_the_settings_router_source_when_read_then_it_has_no_noqa() -> None:
    source = Path(settings_router.__file__).read_text(encoding="utf-8")

    assert "noqa" not in source


# 5
async def test_given_client_request_id_when_answered_then_the_header_is_the_id_source_value(
    surface: AsyncClient,
) -> None:
    first = await surface.get("/healthz", headers={"X-Request-Id": "attacker"})
    second = await surface.get("/healthz", headers={"X-Request-Id": "attacker"})

    assert first.headers["x-request-id"] == "request-1"
    assert second.headers["x-request-id"] == "request-2"


async def test_given_a_request_when_handled_then_the_request_id_is_in_request_state() -> None:
    app = make_app()
    seen: list[str] = []

    @app.get("/t/state", dependencies=[Depends(public)])
    async def state(request: Request) -> None:
        seen.append(request.state.request_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/t/state")

    assert seen == [response.headers["x-request-id"]]


# 6
@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_given_production_when_docs_requested_then_404_problem(path: str) -> None:
    app = make_app(make_settings(environment="production", trusted_proxy_cidrs=["10.244.0.0/16"]))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)

    _assert_generic_problem(response, 404)


# 8
class _RaisingGuard:
    def __init__(self, retry_after_seconds: int) -> None:
        self._retry_after = retry_after_seconds
        self.calls: list[str] = []

    async def check(self, bucket: str, request: Request) -> None:
        self.calls.append(bucket)
        raise RateLimited(self._retry_after)


async def test_given_default_limit_guard_when_route_called_then_it_passes(surface: AsyncClient) -> None:
    response = await surface.get("/t/limited")

    assert response.status_code == 200
    assert response.json() == {"ok": "yes"}


async def test_given_raising_guard_when_route_called_then_429_with_integer_retry_after_and_no_detail(
    surface_app: FastAPI,
) -> None:
    guard = _RaisingGuard(42)
    surface_app.state.limit_guard = guard
    async with AsyncClient(transport=ASGITransport(app=surface_app), base_url="http://test") as client:
        response = await client.get("/t/limited")

    _assert_generic_problem(response, 429)
    assert response.headers["retry-after"] == "42"
    assert guard.calls == ["test-bucket"]
    text = response.text
    assert "test-bucket" not in text
    assert "42" not in json.dumps({k: v for k, v in response.json().items() if k != "status"})
    assert "testclient" not in text.lower()
