"""U-quiet-hours-15a: the migrate job runs as the owner, creates the runtime role and applies the grants (ADR-0025)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic import command
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrate import (
    MIGRATION_LOCK_KEY,
    RUNTIME_ROLE,
    WEB_ROLE,
    MigrationStepFailed,
    SchemaNotReady,
    check_schema,
    expected_head,
    migrate_database,
)
from app.db.purge import PurgeCounts
from schedule_policy.testing import FakeClock
from tests.db.conftest import alembic_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from testcontainers.community.postgres import PostgresContainer

PASSWORD = "runtime-job-test-only"  # noqa: S105  # a throwaway role inside a throwaway test container


WEB_PASSWORD = "web-job-test-only"  # noqa: S105  # a throwaway role inside a throwaway test container
PASSWORDS = {RUNTIME_ROLE: PASSWORD, WEB_ROLE: WEB_PASSWORD}


def _dsn(url: str, *, user: str | None = None, password: str | None = None) -> dict[str, object]:
    parsed = make_url(url)
    return {
        "host": parsed.host,
        "port": parsed.port,
        "user": user or parsed.username,
        "password": password or parsed.password,
        "database": parsed.database,
    }


def _runtime_url(url: str, password: str = PASSWORD) -> str:
    return make_url(url).set(username=RUNTIME_ROLE, password=password).render_as_string(hide_password=False)


SHARED_WEB_PASSWORD = "web-test-password"  # noqa: S105  # what the web role grant tests expect of the shared role
SHARED_TEST_PASSWORD = "runtime-test-only"  # noqa: S105  # what the other database tests expect of the shared role


@pytest.fixture(autouse=True)
async def _leave_the_shared_role_as_found(pg_server: PostgresContainer) -> AsyncIterator[None]:
    """Roles are cluster-wide in the test container; these tests rotate the password, others rely on a fixed one."""
    yield
    connection = await asyncpg.connect(
        host=pg_server.get_container_host_ip(),
        port=int(pg_server.get_exposed_port(5432)),
        user=pg_server.username,
        password=pg_server.password,
        database=pg_server.dbname,
    )
    try:
        if await connection.fetchval("select 1 from pg_roles where rolname = $1", RUNTIME_ROLE):
            await connection.execute(f"ALTER ROLE {RUNTIME_ROLE} PASSWORD '{SHARED_TEST_PASSWORD}'")
        if await connection.fetchval("select 1 from pg_roles where rolname = $1", WEB_ROLE):
            await connection.execute(f"ALTER ROLE {WEB_ROLE} PASSWORD '{SHARED_WEB_PASSWORD}'")
    finally:
        await connection.close()


@pytest.fixture
async def owner(database_url: str) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(**_dsn(database_url))  # type: ignore[arg-type]
    yield connection
    await connection.close()


async def _as_runtime(url: str, password: str = PASSWORD) -> asyncpg.Connection:
    return await asyncpg.connect(**_dsn(url, user=RUNTIME_ROLE, password=password))  # type: ignore[arg-type]


async def test_given_an_empty_database_when_the_job_runs_then_the_schema_the_role_and_the_grants_exist(
    database_url: str, owner: asyncpg.Connection
) -> None:
    await migrate_database(database_url, PASSWORDS)

    tables = {r["tablename"] for r in await owner.fetch("select tablename from pg_tables where schemaname = 'public'")}
    assert {"mail_item", "alert", "conversation", "alembic_version"} <= tables
    role = await owner.fetchrow(
        "select rolsuper, rolcreatedb, rolcreaterole, rolcanlogin from pg_roles where rolname = $1", RUNTIME_ROLE
    )
    assert role is not None
    assert (role["rolsuper"], role["rolcreatedb"], role["rolcreaterole"], role["rolcanlogin"]) == (
        False,
        False,
        False,
        True,
    )
    runtime = await _as_runtime(database_url)
    try:
        assert await runtime.fetchval("select count(*) from mail_item") == 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await runtime.execute("create table evil (id int)")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await runtime.execute("delete from settings.settings_change")
    finally:
        await runtime.close()
    owned = await owner.fetch(
        "select c.relname from pg_class c join pg_roles r on r.oid = c.relowner where r.rolname = $1", RUNTIME_ROLE
    )
    assert owned == []


async def test_given_the_job_has_run_when_it_runs_again_then_nothing_breaks_and_nothing_is_duplicated(
    database_url: str, owner: asyncpg.Connection
) -> None:
    await migrate_database(database_url, PASSWORDS)
    await migrate_database(database_url, PASSWORDS)

    assert await owner.fetchval("select count(*) from pg_roles where rolname = $1", RUNTIME_ROLE) == 1
    assert await owner.fetchval("select count(*) from alembic_version") == 1
    runtime = await _as_runtime(database_url)
    try:
        assert await runtime.fetchval("select count(*) from alert") == 0
    finally:
        await runtime.close()


async def test_given_a_new_password_when_the_job_runs_then_the_runtime_role_uses_it_and_the_old_one_is_dead(
    database_url: str,
) -> None:
    await migrate_database(database_url, PASSWORDS)
    await migrate_database(database_url, {**PASSWORDS, RUNTIME_ROLE: "rotated-test-only"})

    runtime = await _as_runtime(database_url, "rotated-test-only")
    await runtime.close()
    with pytest.raises(asyncpg.InvalidPasswordError):
        await _as_runtime(database_url, PASSWORD)


async def test_given_a_password_with_quotes_and_semicolons_when_the_job_runs_then_it_is_set_literally(
    database_url: str,
) -> None:
    awkward = "o'brien\";--drop role x;"

    await migrate_database(database_url, {**PASSWORDS, RUNTIME_ROLE: awkward})

    runtime = await _as_runtime(database_url, awkward)
    await runtime.close()


async def test_given_another_migration_holds_the_lock_when_the_job_runs_then_it_waits_for_it(
    database_url: str, owner: asyncpg.Connection
) -> None:
    await owner.execute("select pg_advisory_lock($1)", MIGRATION_LOCK_KEY)

    job = asyncio.create_task(migrate_database(database_url, PASSWORDS))
    done, _ = await asyncio.wait({job}, timeout=1.5)
    assert not done, "the job must wait while another migration holds the lock"
    tables = await owner.fetchval("select count(*) from pg_tables where schemaname = 'public'")
    assert tables == 0

    await owner.execute("select pg_advisory_unlock($1)", MIGRATION_LOCK_KEY)
    await asyncio.wait_for(job, timeout=60)


async def test_given_the_job_holds_the_agent_lock_free_when_an_agent_runs_then_the_two_locks_differ() -> None:
    from app.db.repos import LOCK_KEY  # noqa: PLC0415

    assert MIGRATION_LOCK_KEY != LOCK_KEY  # a running old agent must not block the migration job


async def test_given_the_wrong_owner_password_when_the_job_runs_then_the_error_does_not_contain_a_password(
    database_url: str,
) -> None:
    broken = make_url(database_url).set(password="wrong-owner-secret").render_as_string(hide_password=False)

    with pytest.raises(Exception) as error:  # noqa: PT011 - any driver error
        await migrate_database(broken, PASSWORDS)

    assert "wrong-owner-secret" not in str(error.value)
    assert PASSWORD not in str(error.value)


async def test_given_a_database_without_migrations_when_the_schema_is_checked_then_it_is_not_ready(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    try:
        with pytest.raises(SchemaNotReady) as error:
            await check_schema(engine)
    finally:
        await engine.dispose()

    assert "migrate" in str(error.value)


async def test_given_a_schema_behind_the_head_when_it_is_checked_then_it_is_not_ready(database_url: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "0004")
    engine = create_async_engine(database_url)
    try:
        with pytest.raises(SchemaNotReady) as error:
            await check_schema(engine)
    finally:
        await engine.dispose()

    assert "0004" in str(error.value)


async def test_given_the_head_when_the_schema_is_checked_by_the_runtime_role_then_it_is_ready(
    database_url: str,
) -> None:
    await migrate_database(database_url, PASSWORDS)
    engine = create_async_engine(_runtime_url(database_url))
    try:
        await check_schema(engine)
    finally:
        await engine.dispose()


# --- U-web-settings-08: the roles come from a list; the web role is created like the agent role (ADR-0030) ---


async def test_given_two_roles_and_two_passwords_when_the_job_runs_then_both_log_in_with_scram_and_are_hardened(
    database_url: str, owner: asyncpg.Connection
) -> None:
    await migrate_database(database_url, PASSWORDS)

    rows = await owner.fetch(
        "select r.rolname, r.rolcanlogin, r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolinherit, r.rolreplication, "
        "r.rolbypassrls, a.rolpassword from pg_roles r join pg_authid a on a.oid = r.oid where r.rolname = any($1)",
        [RUNTIME_ROLE, WEB_ROLE],
    )
    assert {row["rolname"] for row in rows} == {RUNTIME_ROLE, WEB_ROLE}
    for row in rows:
        assert (row["rolcanlogin"], row["rolsuper"], row["rolcreatedb"], row["rolcreaterole"]) == (
            True,
            False,
            False,
            False,
        )
        assert (row["rolinherit"], row["rolreplication"], row["rolbypassrls"]) == (False, False, False)
        assert str(row["rolpassword"]).startswith("SCRAM-SHA-256$4096:")
    members = await owner.fetchval(
        "select count(*) from pg_auth_members m join pg_roles r on r.oid = m.member where r.rolname = any($1)",
        [RUNTIME_ROLE, WEB_ROLE],
    )
    assert members == 0
    for role, password in PASSWORDS.items():
        connection = await asyncpg.connect(**_dsn(database_url, user=role, password=password))  # type: ignore[arg-type]
        await connection.close()


async def test_given_the_job_has_run_when_the_web_role_is_used_then_it_has_the_rights_of_grants_sql_only(
    database_url: str,
) -> None:
    await migrate_database(database_url, PASSWORDS)

    web = await asyncpg.connect(**_dsn(database_url, user=WEB_ROLE, password=WEB_PASSWORD))  # type: ignore[arg-type]
    try:
        assert await web.fetchval("select count(*) from settings.schedule") == 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await web.execute("select count(*) from mail_item")
    finally:
        await web.close()


async def test_given_the_job_runs_twice_when_compared_then_roles_attributes_and_grants_are_the_same(
    database_url: str, owner: asyncpg.Connection
) -> None:
    snapshot = (
        "select r.rolname, r.rolinherit, r.rolreplication, r.rolbypassrls, "
        "array(select g.privilege_type || ':' || g.table_schema || '.' || g.table_name "
        " from information_schema.role_table_grants g where g.grantee = r.rolname order by 1) as grants "
        "from pg_roles r where r.rolname = any($1) order by r.rolname"
    )
    await migrate_database(database_url, PASSWORDS)
    first = [tuple(row) for row in await owner.fetch(snapshot, [RUNTIME_ROLE, WEB_ROLE])]

    await migrate_database(database_url, PASSWORDS)
    second = [tuple(row) for row in await owner.fetch(snapshot, [RUNTIME_ROLE, WEB_ROLE])]

    assert first == second
    assert len(first) == 2


async def test_given_a_missing_web_role_password_when_the_command_runs_then_it_exits_naming_the_key_and_changes_nothing(
    database_url: str, owner: asyncpg.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.main import EXIT_BAD_CONFIG, main  # noqa: PLC0415

    env = {"DATABASE_OWNER_URL": database_url, "RUNTIME_ROLE_PASSWORD": PASSWORD}  # no WEB_ROLE_PASSWORD

    assert main(env, argv=["migrate"]) == EXIT_BAD_CONFIG

    err = capsys.readouterr().err
    assert "WEB_ROLE_PASSWORD" in err
    assert PASSWORD not in err
    assert database_url not in err
    tables = await owner.fetchval("select count(*) from pg_tables where schemaname = 'public'")
    assert tables == 0  # not even the schema was touched


# --- U-web-settings-49: the purge is the last step of the job (AC-21) ---


async def test_given_the_job_when_it_runs_then_the_purge_comes_after_the_migration_and_the_grants(
    database_url: str, owner: asyncpg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    async def spy(connection: asyncpg.Connection, clock: object) -> PurgeCounts:
        seen["head"] = await connection.fetchval("select version_num from alembic_version")
        seen["grant"] = await connection.fetchval(
            "select has_table_privilege($1, 'web_auth.session', 'SELECT')", WEB_ROLE
        )
        seen["clock"] = clock
        return PurgeCounts(0, 0, 0, 0, 0)

    monkeypatch.setattr("app.db.migrate.purge_expired", spy)
    clock = FakeClock()

    await migrate_database(database_url, PASSWORDS, clock=clock)

    assert seen == {"head": expected_head(), "grant": True, "clock": clock}


async def test_given_a_failing_purge_when_the_job_runs_then_it_raises_naming_the_step_and_no_secret(
    database_url: str, owner: asyncpg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(connection: asyncpg.Connection, clock: object) -> PurgeCounts:
        raise RuntimeError("postgresql://owner:hunter2@db/x")

    monkeypatch.setattr("app.db.migrate.purge_expired", boom)

    with pytest.raises(MigrationStepFailed) as failed:
        await migrate_database(database_url, PASSWORDS)

    assert failed.value.step == "purge"
    assert "purge" in str(failed.value)
    assert "hunter2" not in str(failed.value)
    assert await owner.fetchval("select 1 from pg_roles where rolname = $1", RUNTIME_ROLE) == 1  # earlier steps stand


async def test_given_the_job_when_it_runs_then_old_audit_rows_are_removed_in_the_same_run(
    database_url: str, owner: asyncpg.Connection
) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(database_url), "head")
    await owner.execute(
        "insert into settings.settings_change (at, via, by, db_role, new) "
        "values (now() - interval '400 days', 'web', 'x', 'r', '{}')"
    )

    await migrate_database(database_url, PASSWORDS)

    assert await owner.fetchval("select count(*) from settings.settings_change") == 0
