"""U-mail-categories-04 follow-up: a body limit per route, with the global limit as the default (MC-12)."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.middleware import BodyLimitMiddleware
from app.startup import ConfigurationError, validate_startup
from tests.fakes import make_app, make_settings

LIST_LIMIT = 32768
# A full list: 50 categories with a 500 character description is about 27 KB.
FULL_LIST = 27 * 1024


def _http(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.50", 5000)), base_url="http://test")


def _wrapped(limits: dict[str, int]) -> FastAPI:
    inner = FastAPI()

    @inner.put("/api/categories")
    async def put_categories(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    @inner.post("/api/categories")
    async def post_categories(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    @inner.put("/api/other")
    async def put_other(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    inner.add_middleware(BodyLimitMiddleware, limit_bytes=8192, route_limits=limits)
    return inner


LIMITS = {"PUT /api/categories": LIST_LIMIT}


async def test_given_the_default_settings_when_read_then_the_list_route_has_32_kb_and_the_rest_8_kb() -> None:
    settings = make_settings()

    assert settings.body_limit_bytes == 8192
    assert settings.route_body_limits == {"PUT /api/categories": LIST_LIMIT}


async def test_given_a_full_list_body_when_put_to_the_list_route_then_it_is_not_refused_as_too_large() -> None:
    async with _http(make_app(make_settings())) as http:
        response = await http.put("/api/categories", content=b"x" * FULL_LIST)

    assert response.status_code != 413


async def test_given_the_list_limit_when_put_with_content_length_then_the_edge_is_32768_and_32769_gives_413() -> None:
    async with _http(_wrapped(LIMITS)) as http:
        ok = await http.put("/api/categories", content=b"x" * LIST_LIMIT)
        big = await http.put("/api/categories", content=b"x" * (LIST_LIMIT + 1))

    assert ok.status_code == 200
    assert big.status_code == 413


async def test_given_the_real_app_when_put_32_kb_plus_one_then_413_with_the_generic_body_and_no_store() -> None:
    async with _http(make_app(make_settings())) as http:
        big = await http.put("/api/categories", content=b"x" * (LIST_LIMIT + 1))

    assert big.status_code == 413
    assert big.json() == {"type": "about:blank", "title": "Payload too large", "status": 413}
    assert big.headers["content-type"] == "application/problem+json"
    assert big.headers["cache-control"] == "no-store"
    assert big.headers["x-request-id"]


async def test_given_the_list_limit_when_a_chunked_body_is_sent_then_it_is_enforced_at_32_kb() -> None:
    async def chunks(total: int) -> AsyncIterator[bytes]:
        for _ in range(total // 1024):
            yield b"x" * 1024

    async with _http(_wrapped(LIMITS)) as http:
        ok = await http.put("/api/categories", content=chunks(FULL_LIST))
        big = await http.put("/api/categories", content=chunks(LIST_LIMIT + 1024))

    assert ok.status_code == 200
    assert big.status_code == 413


async def test_given_the_real_app_when_a_chunked_body_passes_32_kb_then_413_with_no_store() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(33):
            yield b"x" * 1024

    async with _http(make_app(make_settings())) as http:
        big = await http.put("/api/categories", content=chunks())

    assert big.status_code == 413
    assert big.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("method", "path"),
    [("PUT", "/api/other"), ("POST", "/api/categories")],
)
async def test_given_a_route_without_its_own_limit_when_sent_8_kb_plus_one_then_413(method: str, path: str) -> None:
    async with _http(_wrapped(LIMITS)) as http:
        ok = await http.request(method, path, content=b"x" * 8192)
        big = await http.request(method, path, content=b"x" * 8193)

    assert ok.status_code == 200
    assert big.status_code == 413


async def test_given_the_real_app_when_another_route_gets_8_kb_plus_one_then_413() -> None:
    async with _http(make_app(make_settings())) as http:
        big = await http.post("/auth/verify-code", content=b"x" * 8193)

    assert big.status_code == 413


async def test_given_a_route_limit_in_the_settings_when_lowered_then_it_takes_effect() -> None:
    app = make_app(make_settings(route_body_limits={"PUT /api/categories": 100}))
    async with _http(app) as http:
        big = await http.put("/api/categories", content=b"x" * 101)

    assert big.status_code == 413


@pytest.mark.parametrize("limits", [{"PUT /api/categories": 0}, {"/api/categories": 10}, {"PUT api": 10}])
def test_given_a_wrong_route_limit_when_the_app_starts_then_startup_refuses_it(limits: dict[str, int]) -> None:
    with pytest.raises(ConfigurationError) as raised:
        validate_startup(make_settings(route_body_limits=limits))

    assert "route_body_limits" in str(raised.value)
