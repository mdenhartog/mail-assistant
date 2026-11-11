"""The legacy ``create_app`` keeps its behaviour until U-web-settings-38: no new HTTP surface on it."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import create_app


async def test_given_legacy_factory_when_unknown_path_then_framework_default_without_surface_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/does-not-exist")
        health = await client.get("/healthz")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert "x-request-id" not in health.headers
    assert health.json() == {"status": "ok"}
