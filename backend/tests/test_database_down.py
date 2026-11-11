"""U-web-settings-09: with the database down, /readyz is 503 and the log shows no URL and no password."""

import logging
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import Database
from app.startup import attach_database
from tests.fakes import FakeClock, make_app

CANARY = "canary-smtp-secret"  # also on the canary list of tests/conftest.py, which fails the test if it is logged
URL = f"postgresql+asyncpg://web_settings_runtime:{CANARY}@127.0.0.1:1/canary-db"


@pytest.fixture
async def down_client() -> AsyncIterator[AsyncClient]:
    database = Database.create(URL, ssl_context=None, statement_timeout_ms=1000)
    app = make_app()
    attach_database(app, database, FakeClock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await database.dispose()


async def test_given_the_database_is_down_when_readyz_then_503_and_the_log_has_class_and_sqlstate_only(
    down_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    response = await down_client.get("/readyz")

    assert response.status_code == 503
    messages = [record.getMessage() for record in caplog.records]
    unavailable = [m for m in messages if m.startswith("database.unavailable")]
    assert len(unavailable) == 1
    assert "error_class=" in unavailable[0]
    assert "sqlstate=" in unavailable[0]
    for text in (*messages, response.text, repr(caplog.records)):
        assert CANARY not in text
        assert "127.0.0.1" not in text
        assert "canary-db" not in text


async def test_given_an_app_without_a_database_when_readyz_then_200_as_the_legacy_factory_expects() -> None:
    app = make_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/readyz")).status_code == 200
