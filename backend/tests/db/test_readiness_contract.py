"""U-web-settings-65, criterion 1: /readyz is 503 on a database older or newer than the api, 200 at its own version.

The chain is really walked down with the agent's Alembic (a subprocess: it has its own ``app``), so the test proves
that migrations 0009 to 0011 cannot pass for the version the api expects.
"""

import os
import subprocess  # the agent's Alembic environment must not share this process
import sys
from collections.abc import AsyncIterator

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.db import EXPECTED_CONTRACT_VERSION, Database
from app.startup import attach_database
from tests.db.conftest import AGENT_ROOT, DbEndpoint
from tests.fakes import FakeClock, make_app

_DOWNGRADE = (
    "import os\n"
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', 'migrations')\n"
    "config.set_main_option('sqlalchemy.url', os.environ['MIGRATE_URL'])\n"
    "command.downgrade(config, os.environ['TARGET'])\n"
)


def _walk_down(db: DbEndpoint, target: str) -> None:
    result = subprocess.run(  # noqa: S603  # a fixed interpreter and a fixed script
        [sys.executable, "-c", _DOWNGRADE],
        cwd=AGENT_ROOT,
        env={**os.environ, "MIGRATE_URL": db.owner_url, "TARGET": target},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.fixture
async def ready_client(web_database: Database) -> AsyncIterator[AsyncClient]:
    app = make_app()
    attach_database(app, web_database, FakeClock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def test_given_the_api_when_it_is_built_then_it_expects_version_2() -> None:
    assert EXPECTED_CONTRACT_VERSION == 2


async def test_given_the_chain_at_0012_when_readyz_then_200(ready_client: AsyncClient) -> None:
    response = await ready_client.get("/readyz")

    assert response.status_code == 200


@pytest.mark.parametrize("revision", ["0011", "0010", "0009"])
async def test_given_the_chain_at_an_older_revision_when_readyz_then_503(
    ready_client: AsyncClient, db: DbEndpoint, revision: str
) -> None:
    _walk_down(db, revision)

    response = await ready_client.get("/readyz")

    assert response.status_code == 503
    assert "contract" not in response.text.lower()


async def test_given_a_newer_database_when_readyz_then_503(
    ready_client: AsyncClient, owner: asyncpg.Connection
) -> None:
    await owner.execute(
        "CREATE OR REPLACE FUNCTION settings.contract_version() RETURNS integer "
        "LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$ SELECT 3 $$"
    )

    response = await ready_client.get("/readyz")

    assert response.status_code == 503
