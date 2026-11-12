from httpx import AsyncClient

from tests.fakes import make_app, make_settings


async def test_given_running_app_when_get_healthz_then_status_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_given_app_without_database_when_get_readyz_then_503_and_not_ready(client: AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 503


async def test_given_unknown_path_when_requested_then_404(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404


def test_given_settings_when_app_created_then_app_name_is_the_title() -> None:
    app = make_app(make_settings(app_name="Test Name"))

    assert app.title == "Test Name"


def test_given_production_when_app_created_then_docs_disabled() -> None:
    app = make_app(make_settings(environment="production"))

    assert app.docs_url is None
    assert app.openapi_url is None
