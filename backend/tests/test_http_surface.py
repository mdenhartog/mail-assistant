"""HTTP surface: error model, headers, request id and the limit seam (U-web-settings-05)."""

import json
import logging

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from httpx import ASGITransport, AsyncClient, Response

from app.core.security import public, session
from app.errors import PROBLEM_MEDIA_TYPE, ProblemError, RateLimited
from app.limit_guard import limit
from tests.fakes import make_app, make_settings

SECURITY_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}
CSP_DIRECTIVES = {"script-src 'self'", "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'"}


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


# 4
async def test_given_html_response_when_inspected_then_csp_has_exactly_the_four_directives(
    surface: AsyncClient,
) -> None:
    response = await surface.get("/t/html")

    csp = response.headers["content-security-policy"]
    assert {part.strip() for part in csp.split(";")} == CSP_DIRECTIVES
    assert "unsafe-inline" not in csp


async def test_given_json_response_when_inspected_then_no_csp(surface: AsyncClient) -> None:
    response = await surface.get("/healthz")

    assert "content-security-policy" not in response.headers


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
    app = make_app(make_settings(environment="production"))

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
