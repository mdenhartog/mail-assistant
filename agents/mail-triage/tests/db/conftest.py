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
    from collections.abc import AsyncIterator, Iterator

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


# --- The categories schema (U-mail-categories-03): both runtime roles, without their passwords ----------------------
API_ROLE = "web_settings_runtime"  # the api's login (ADR-0033)
AGENT_ROLE = "mail_triage_runtime"  # the agent's login
GRANTS = ROOT / "app" / "db" / "grants.sql"
_ENSURE_ROLES = f"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{API_ROLE}') THEN
        CREATE ROLE {API_ROLE} LOGIN PASSWORD 'test-unused-api' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{AGENT_ROLE}') THEN
        CREATE ROLE {AGENT_ROLE} LOGIN PASSWORD 'test-unused-agent' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$
"""  # noqa: S608  # fixed role names of this module


def plain_url(url: str) -> str:
    """The asyncpg form of a SQLAlchemy URL."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def connect_as(url: str, role: str | None) -> asyncpg.Connection:
    """A connection whose ``session_user`` is ``role`` (the container's superuser when None).

    The superuser connects and switches the session authorization, so the tests never need the role's password and
    the triggers see the same ``session_user`` as for a real login.
    """
    connection = await asyncpg.connect(plain_url(url))
    if role is not None:
        await connection.execute(f'SET SESSION AUTHORIZATION "{role}"')
    return connection


async def _create_database(server: PostgresContainer, name: str, template: str | None = None) -> None:
    connection = await asyncpg.connect(
        host=server.get_container_host_ip(),
        port=int(server.get_exposed_port(5432)),
        user=server.username,
        password=server.password,
        database=server.dbname,
    )
    try:
        await connection.execute(f'CREATE DATABASE "{name}"' + (f' TEMPLATE "{template}"' if template else ""))
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def categories_template(pg_server: PostgresContainer) -> str:
    """One database migrated to head, used as the template of every categories test (a copy costs milliseconds)."""
    name = f"tpl_{uuid.uuid4().hex[:10]}"
    asyncio.run(_create_database(pg_server, name))
    host, port = pg_server.get_container_host_ip(), int(pg_server.get_exposed_port(5432))
    url = f"postgresql+asyncpg://{pg_server.username}:{pg_server.password}@{host}:{port}/{name}"
    command.upgrade(alembic_config(url), "head")
    return name


@pytest.fixture
def cat_url(pg_server: PostgresContainer, categories_template: str) -> str:
    """A fresh copy of the migrated template database, as an asyncpg URL."""
    name = f"t_{uuid.uuid4().hex[:10]}"
    asyncio.run(_create_database(pg_server, name, categories_template))
    host, port = pg_server.get_container_host_ip(), int(pg_server.get_exposed_port(5432))
    return f"postgresql+asyncpg://{pg_server.username}:{pg_server.password}@{host}:{port}/{name}"


@pytest.fixture
async def cat_owner(cat_url: str) -> AsyncIterator[asyncpg.Connection]:
    """The owner (superuser) with both runtime roles made, grants.sql applied and the mailbox ``mb1`` and ``mb2``."""
    connection = await connect_as(cat_url, None)
    await connection.execute(_ENSURE_ROLES)
    await connection.execute(GRANTS.read_text(encoding="utf-8"))
    await connection.execute("insert into categories.mailbox (id) values ('mb1'), ('mb2')")
    yield connection
    await connection.close()


@pytest.fixture
async def cat_api(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection acting as the api role."""
    connection = await connect_as(cat_url, API_ROLE)
    yield connection
    await connection.close()


@pytest.fixture
async def cat_agent(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection acting as the agent role."""
    connection = await connect_as(cat_url, AGENT_ROLE)
    yield connection
    await connection.close()


async def write_list(connection: asyncpg.Connection, mailbox: str, version: int, names: list[str]) -> None:
    """Write one list version the way the api does: version, identities and categories in one transaction."""
    async with connection.transaction():
        await insert_list(connection, mailbox, version, names)


async def insert_list(connection: asyncpg.Connection, mailbox: str, version: int, names: list[str]) -> None:
    """The statements of ``write_list`` without the transaction, for tests that control it."""
    await connection.execute(
        "insert into categories.list_version (mailbox_id, version) values ($1, $2)", mailbox, version
    )
    for position, name in enumerate(names):
        identity = uuid.uuid4()
        await connection.execute(
            "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", mailbox, identity
        )
        await connection.execute(
            "insert into categories.category (mailbox_id, version, id, name, description, position) "
            "values ($1, $2, $3, $4, $5, $6)",
            mailbox,
            version,
            identity,
            name,
            f"about {name}",
            position,
        )
