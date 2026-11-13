"""The shared database fixture (U-web-settings-09): a real PostgreSQL, the agent's migration chain, its grants.

One container per session. The agent's chain and ``grants.sql`` run once, as the owner, into a template database; every
test gets its own copy of it, so every test starts from the same clean schema state. Three kinds of connection:
the owner (the container's superuser), the web role and the agent role, each with the rights the grants give it.
"""

from __future__ import annotations

import asyncio
import os
import subprocess  # the agent's Alembic environment must not share this process: it has its own ``app``
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NoReturn

import asyncpg
import pytest
from docker.errors import APIError, DockerException
from requests.exceptions import ConnectionError as RequestsConnectionError
from testcontainers.community.postgres import PostgresContainer

from app.db import Database

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Mapping

AGENT_ROOT = Path(__file__).resolve().parents[3] / "agents" / "mail-triage"
GRANTS = AGENT_ROOT / "app" / "db" / "grants.sql"
IMAGE = "postgres:16-alpine"
WEB_ROLE = "web_settings_runtime"
AGENT_ROLE = "mail_triage_runtime"
WEB_PASSWORD = "test-web-role-pw"  # noqa: S105  # a throwaway role inside a throwaway test container
AGENT_PASSWORD = "test-agent-role-pw"  # noqa: S105
STATEMENT_TIMEOUT_MS = 5000

_MIGRATE = (
    "import os\n"
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', 'migrations')\n"
    "config.set_main_option('sqlalchemy.url', os.environ['MIGRATE_URL'])\n"
    "command.upgrade(config, 'head')\n"
)
_CREATE_ROLES = f"""
CREATE ROLE {WEB_ROLE} LOGIN PASSWORD '{WEB_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE {AGENT_ROLE} LOGIN PASSWORD '{AGENT_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
"""


@dataclass(frozen=True)
class Server:
    """The PostgreSQL container: where it is and the owner's credentials."""

    host: str
    port: int
    user: str
    password: str
    admin_database: str

    def url(self, user: str, password: str, database: str) -> str:
        return f"postgresql+asyncpg://{user}:{password}@{self.host}:{self.port}/{database}"

    async def connect(self, database: str | None = None, *, user: str | None = None, password: str | None = None):
        return await asyncpg.connect(
            host=self.host,
            port=self.port,
            user=user or self.user,
            password=password or self.password,
            database=database or self.admin_database,
        )


@dataclass(frozen=True)
class DbEndpoint:
    """One test's database and how to reach it as each role (asyncpg URLs for SQLAlchemy)."""

    name: str
    owner_url: str
    web_url: str
    agent_url: str


def _docker_unavailable(error: BaseException) -> bool:
    """Whether the error says there is no Docker to talk to (no daemon, no socket), not that a container failed."""
    if isinstance(error, APIError):
        return False  # the daemon answered and refused: a real fault
    return isinstance(error, DockerException | RequestsConnectionError | FileNotFoundError | ConnectionError)


def start_failure_outcome(error: BaseException, *, ci: bool) -> Literal["skip", "fail"]:
    """Decide what a failed container start means (CR-02): a skip only without Docker and only outside CI."""
    return "skip" if not ci and _docker_unavailable(error) else "fail"


def report_start_failure(error: BaseException, image: str, env: Mapping[str, str]) -> NoReturn:
    """Skip or fail the run for a container that did not start; ``CI`` set and not empty means a continuous run."""
    detail = f"{image} did not start: {type(error).__name__}"
    if start_failure_outcome(error, ci=bool(env.get("CI"))) == "skip":
        pytest.skip(f"Docker is needed for the database tests ({detail})")
    pytest.fail(detail, pytrace=False)


@pytest.fixture(scope="session")
def pg_server() -> Iterator[PostgresContainer]:
    try:
        container = PostgresContainer(IMAGE, driver=None)
        container.start()
    except Exception as error:
        report_start_failure(error, IMAGE, os.environ)
    yield container
    container.stop()


@pytest.fixture(scope="session")
def server(pg_server: PostgresContainer) -> Server:
    return Server(
        host=pg_server.get_container_host_ip(),
        port=int(pg_server.get_exposed_port(5432)),
        user=pg_server.username,
        password=pg_server.password,
        admin_database=pg_server.dbname,
    )


async def _prepare(server: Server, name: str) -> None:
    admin = await server.connect()
    try:
        await admin.execute(_CREATE_ROLES)
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()


async def _grant(server: Server, name: str) -> None:
    owner = await server.connect(name)
    try:
        await owner.execute(GRANTS.read_text(encoding="utf-8"))
    finally:
        await owner.close()


@pytest.fixture(scope="session")
def template_name(server: Server) -> str:
    """Create the two login roles, migrate a template database as the owner and apply the agent's grants once."""
    name = f"tpl_{uuid.uuid4().hex[:10]}"
    asyncio.run(_prepare(server, name))
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _MIGRATE],
        cwd=AGENT_ROOT,
        env={**os.environ, "MIGRATE_URL": server.url(server.user, server.password, name)},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"the agent's migration chain failed:\n{result.stderr[-2000:]}", pytrace=False)
    asyncio.run(_grant(server, name))
    return name


@pytest.fixture
async def db(server: Server, template_name: str) -> AsyncIterator[DbEndpoint]:
    """A fresh copy of the migrated, granted template for this test alone."""
    name = f"t_{uuid.uuid4().hex[:10]}"
    admin = await server.connect()
    try:
        await admin.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template_name}"')
    finally:
        await admin.close()
    yield DbEndpoint(
        name=name,
        owner_url=server.url(server.user, server.password, name),
        web_url=server.url(WEB_ROLE, WEB_PASSWORD, name),
        agent_url=server.url(AGENT_ROLE, AGENT_PASSWORD, name),
    )
    admin = await server.connect()
    try:
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.fixture
async def owner(db: DbEndpoint, server: Server) -> AsyncIterator[asyncpg.Connection]:
    """A connection as the owner of the schema (the test container's superuser)."""
    connection = await server.connect(db.name)
    yield connection
    await connection.close()


@pytest.fixture
async def agent(db: DbEndpoint, server: Server) -> AsyncIterator[asyncpg.Connection]:
    """A connection as the agent's runtime role."""
    connection = await server.connect(db.name, user=AGENT_ROLE, password=AGENT_PASSWORD)
    yield connection
    await connection.close()


@pytest.fixture
async def web_database(db: DbEndpoint) -> AsyncIterator[Database]:
    """The application's own database access, connected as the web role (no TLS: the test container has none)."""
    database = Database.create(db.web_url, ssl_context=None, statement_timeout_ms=STATEMENT_TIMEOUT_MS)
    yield database
    await database.dispose()
