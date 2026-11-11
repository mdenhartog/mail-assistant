"""U-quiet-hours-16b: the migrate job sets a SCRAM verifier and refuses a widened runtime role (ADR-0030).

These tests need their own PostgreSQL: it logs every statement it receives (``log_statement=all``), which is the
evidence that the clear password never reaches the server.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

import asyncpg
import pytest
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

from app.db.migrate import RUNTIME_ROLE, WEB_ROLE, RuntimeRoleNotSafe, migrate_database
from app.settings import MigrateSettings
from app.wiring import EXIT_MIGRATION_FAILED, migrate
from tests.db.conftest import IMAGE

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

PASSWORD = "clear-pw-NEVER-in-a-log-9f3a"  # noqa: S105  # a throwaway role inside a throwaway test container
WEB_PASSWORD = "clear-web-pw-NEVER-in-a-log-71cc"  # noqa: S105  # same
PASSWORDS = {RUNTIME_ROLE: PASSWORD, WEB_ROLE: WEB_PASSWORD}


@pytest.fixture(scope="module")
def logging_server() -> Iterator[PostgresContainer]:
    try:
        container = PostgresContainer(IMAGE, driver=None).with_command("postgres -c log_statement=all")
        container.start()
    except Exception as error:
        pytest.skip(f"Docker with {IMAGE} is needed for the persistence tests: {type(error).__name__}")
    yield container
    container.stop()


@pytest.fixture
def owner_url(logging_server: PostgresContainer) -> str:
    name = f"t_{uuid.uuid4().hex[:10]}"
    host, port = logging_server.get_container_host_ip(), int(logging_server.get_exposed_port(5432))

    async def create() -> None:
        connection = await asyncpg.connect(
            host=host,
            port=port,
            user=logging_server.username,
            password=logging_server.password,
            database=logging_server.dbname,
        )
        try:
            await connection.execute(f'CREATE DATABASE "{name}"')
        finally:
            await connection.close()

    asyncio.run(create())
    user, secret = logging_server.username, logging_server.password
    return f"postgresql+asyncpg://{user}:{secret}@{host}:{port}/{name}?ssl=disable"


@pytest.fixture
async def owner(owner_url: str) -> AsyncIterator[asyncpg.Connection]:
    parsed = make_url(owner_url)
    connection = await asyncpg.connect(
        host=parsed.host, port=parsed.port, user=parsed.username, password=parsed.password, database=parsed.database
    )
    yield connection
    await connection.close()


@pytest.fixture(autouse=True)
async def _reset_the_cluster_wide_role(logging_server: PostgresContainer) -> AsyncIterator[None]:
    """Roles live in the whole cluster; every test ends by taking back the memberships it granted."""
    yield
    connection = await asyncpg.connect(
        host=logging_server.get_container_host_ip(),
        port=int(logging_server.get_exposed_port(5432)),
        user=logging_server.username,
        password=logging_server.password,
        database=logging_server.dbname,
    )
    try:
        granted = await connection.fetch(
            "select g.rolname from pg_auth_members m join pg_roles g on g.oid = m.roleid "
            "join pg_roles r on r.oid = m.member where r.rolname = $1",
            RUNTIME_ROLE,
        )
        for row in granted:
            await connection.execute(f'REVOKE "{row["rolname"]}" FROM {RUNTIME_ROLE}')
        web_granted = await connection.fetch(
            "select g.rolname from pg_auth_members m join pg_roles g on g.oid = m.roleid "
            "join pg_roles r on r.oid = m.member where r.rolname = $1",
            WEB_ROLE,
        )
        for row in web_granted:
            await connection.execute(f'REVOKE "{row["rolname"]}" FROM {WEB_ROLE}')
    finally:
        await connection.close()


async def test_given_a_real_server_when_the_job_sets_the_password_then_the_agent_logs_in_over_scram_and_no_log_has_it(
    owner_url: str, owner: asyncpg.Connection, logging_server: PostgresContainer
) -> None:
    await migrate_database(owner_url, PASSWORDS)

    stored = await owner.fetchval("select rolpassword from pg_authid where rolname = $1", RUNTIME_ROLE)
    assert str(stored).startswith("SCRAM-SHA-256$4096:")
    parsed = make_url(owner_url)
    runtime = await asyncpg.connect(
        host=parsed.host, port=parsed.port, user=RUNTIME_ROLE, password=PASSWORD, database=parsed.database
    )
    try:
        assert await runtime.fetchval("select 1") == 1
    finally:
        await runtime.close()
    stdout, stderr = logging_server.get_logs()
    server_log = (stdout + stderr).decode("utf-8", errors="replace")
    assert "CREATE ROLE" in server_log or "ALTER ROLE" in server_log  # the server did log the statements
    assert PASSWORD not in server_log
    assert WEB_PASSWORD not in server_log
    web_stored = await owner.fetchval("select rolpassword from pg_authid where rolname = $1", WEB_ROLE)
    assert str(web_stored).startswith("SCRAM-SHA-256$4096:")
    web = await asyncpg.connect(
        host=parsed.host, port=parsed.port, user=WEB_ROLE, password=WEB_PASSWORD, database=parsed.database
    )
    await web.close()


async def test_given_a_runtime_role_with_replication_when_the_job_runs_then_replication_and_bypassrls_are_off(
    owner_url: str, owner: asyncpg.Connection
) -> None:
    await migrate_database(owner_url, PASSWORDS)
    await owner.execute(f"ALTER ROLE {RUNTIME_ROLE} REPLICATION BYPASSRLS")

    await migrate_database(owner_url, PASSWORDS)

    role = await owner.fetchrow("select rolreplication, rolbypassrls from pg_roles where rolname = $1", RUNTIME_ROLE)
    assert role is not None
    assert (role["rolreplication"], role["rolbypassrls"]) == (False, False)


async def test_given_a_runtime_role_with_a_membership_when_the_job_runs_then_it_fails_naming_the_role_not_the_password(
    owner_url: str, owner: asyncpg.Connection
) -> None:
    await migrate_database(owner_url, PASSWORDS)
    await owner.execute(f"GRANT pg_read_all_data TO {RUNTIME_ROLE}")

    with pytest.raises(RuntimeRoleNotSafe) as error:
        await migrate_database(owner_url, PASSWORDS)

    assert RUNTIME_ROLE in str(error.value)
    assert PASSWORD not in str(error.value)


async def test_given_a_runtime_role_with_a_membership_when_the_command_runs_then_exit_6_and_the_log_names_the_role(
    owner_url: str, owner: asyncpg.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    await migrate_database(owner_url, PASSWORDS)
    await owner.execute(f"GRANT pg_read_all_data TO {RUNTIME_ROLE}")
    settings = MigrateSettings(
        database_owner_url=SecretStr(owner_url),
        runtime_role_password=SecretStr(PASSWORD),
        web_role_password=SecretStr(WEB_PASSWORD),
    )

    with caplog.at_level(logging.ERROR):
        code = await migrate(settings)

    assert code == EXIT_MIGRATION_FAILED == 6
    assert RUNTIME_ROLE in caplog.text
    assert PASSWORD not in caplog.text
    assert owner_url not in caplog.text


async def test_given_a_web_role_with_replication_and_a_membership_when_the_job_runs_then_it_resets_and_exits_6(
    owner_url: str, owner: asyncpg.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    await migrate_database(owner_url, PASSWORDS)
    await owner.execute(f"ALTER ROLE {WEB_ROLE} REPLICATION BYPASSRLS")
    await owner.execute(f"GRANT pg_read_all_data TO {WEB_ROLE}")
    settings = MigrateSettings(
        database_owner_url=SecretStr(owner_url),
        runtime_role_password=SecretStr(PASSWORD),
        web_role_password=SecretStr(WEB_PASSWORD),
    )

    with caplog.at_level(logging.ERROR):
        code = await migrate(settings)

    assert code == EXIT_MIGRATION_FAILED == 6
    assert WEB_ROLE in caplog.text
    assert WEB_PASSWORD not in caplog.text
    assert owner_url not in caplog.text
    role = await owner.fetchrow("select rolreplication, rolbypassrls from pg_roles where rolname = $1", WEB_ROLE)
    assert role is not None
    assert (role["rolreplication"], role["rolbypassrls"]) == (False, False)  # reset even though the job failed
