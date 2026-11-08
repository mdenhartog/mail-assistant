"""A real PostgreSQL for the persistence tests (guardrail-pytest: testcontainers, no database mocks)."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "postgres:16-alpine"


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def pg_server() -> Iterator[PostgresContainer]:
    try:
        container = PostgresContainer(IMAGE, driver=None)
        container.start()
    except Exception as error:
        pytest.skip(f"Docker with {IMAGE} is needed for the persistence tests: {type(error).__name__}")
    yield container
    container.stop()


@pytest.fixture
def database_url(pg_server: PostgresContainer) -> str:
    """A fresh, empty database inside the shared container, as an asyncpg URL."""
    name = f"t_{uuid.uuid4().hex[:10]}"
    host, port = pg_server.get_container_host_ip(), int(pg_server.get_exposed_port(5432))

    async def create() -> None:
        connection = await asyncpg.connect(
            host=host, port=port, user=pg_server.username, password=pg_server.password, database=pg_server.dbname
        )
        try:
            await connection.execute(f'CREATE DATABASE "{name}"')
        finally:
            await connection.close()

    asyncio.run(create())
    return f"postgresql+asyncpg://{pg_server.username}:{pg_server.password}@{host}:{port}/{name}"


@pytest.fixture
def migrated_url(database_url: str) -> str:
    command.upgrade(alembic_config(database_url), "head")
    return database_url
