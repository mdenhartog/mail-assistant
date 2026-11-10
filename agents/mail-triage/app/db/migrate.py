"""The schema lifecycle (ADR-0025): the migrate job brings it up to date, the running agent only checks it.

``migrate_database`` is what ``python -m app migrate`` runs. It connects as the owner role, takes a lock so two jobs
never migrate at the same time, applies the Alembic migrations, creates or updates the login role the agent runs with
and applies ``grants.sql``. Every step can be repeated. ``check_schema`` is the agent's readiness check at start-up:
it runs as the runtime role, which owns nothing and cannot change the schema.

Alembic's environment starts its own event loop, so the upgrade runs in a worker thread.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
GRANTS = Path(__file__).resolve().parent / "grants.sql"
RUNTIME_ROLE = "mail_triage_runtime"  # fixed: grants.sql names it
# Not the agent's single-replica lock: the old agent, still running while the job of a new release migrates, holds that.
MIGRATION_LOCK_KEY = 7_265_002


class SchemaNotReady(RuntimeError):  # noqa: N818 - reads as a state, not as an error class
    """The database is not at the Alembic head this build expects. The message holds revisions only, never a URL."""


def _config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _upgrade(url: str) -> None:
    command.upgrade(_config(url), "head")


async def upgrade(url: str) -> None:
    """Apply every migration that has not run yet."""
    await asyncio.to_thread(_upgrade, url)


def expected_head() -> str:
    """The revision this build of the agent needs."""
    head = ScriptDirectory.from_config(_config("")).get_current_head()
    if head is None:  # pragma: no cover - the image always carries migrations
        raise RuntimeError("no migrations found")
    return head


async def check_schema(engine: AsyncEngine) -> None:
    """Raise ``SchemaNotReady`` unless the database is at the head this build expects."""
    expected = expected_head()
    try:
        async with engine.connect() as connection:
            found = (await connection.execute(text("select version_num from alembic_version"))).scalar_one_or_none()
    except DBAPIError:
        found = None  # no table yet (or not readable): same remedy, run the migrate job
    if found != expected:
        raise SchemaNotReady(
            f"database schema is at {found or 'no revision'}, this build needs {expected}; run the migrate job first"
        )


async def _connect(url: str) -> asyncpg.Connection:
    parsed = make_url(url)
    return await asyncpg.connect(
        host=parsed.host, port=parsed.port, user=parsed.username, password=parsed.password, database=parsed.database
    )


async def _ensure_runtime_role(connection: asyncpg.Connection, password: str) -> None:
    """Create the runtime role, or set its password again, so the secret store stays the single source of it.

    The statement is built by the server (``format`` with ``%I`` and ``%L``), so the password is quoted as a literal
    whatever it contains.
    """
    exists = await connection.fetchval("select 1 from pg_roles where rolname = $1", RUNTIME_ROLE)
    statement = await connection.fetchval(
        "select format('%s ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', "
        "$1::text, $2::text, $3::text)",
        "ALTER" if exists else "CREATE",
        RUNTIME_ROLE,
        password,
    )
    await connection.execute(str(statement))


async def migrate_database(owner_url: str, runtime_password: str) -> None:
    """Migrate as the owner, then make the runtime role and its grants match this build. Safe to run again."""
    lock = await _connect(owner_url)
    try:
        await lock.execute("select pg_advisory_lock($1)", MIGRATION_LOCK_KEY)  # waits for a job that is still running
        await upgrade(owner_url)
        async with lock.transaction():
            await _ensure_runtime_role(lock, runtime_password)
            await lock.execute(GRANTS.read_text(encoding="utf-8"))
    finally:
        await lock.close()  # closing the connection also releases the lock
