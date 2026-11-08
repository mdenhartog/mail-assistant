from httpx import AsyncClient

from app.config import Settings, get_settings
from app.main import create_app


async def test_given_running_app_when_get_healthz_then_status_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_given_running_app_when_get_readyz_then_status_ok(client: AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_given_unknown_path_when_requested_then_404(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404


def test_given_no_explicit_settings_when_app_created_then_environment_settings_are_used() -> None:
    get_settings.cache_clear()

    app = create_app()

    assert app.title == get_settings().app_name


def test_given_production_when_app_created_then_docs_disabled() -> None:
    app = create_app(Settings(environment="production"))

    assert app.docs_url is None
    assert app.openapi_url is None
