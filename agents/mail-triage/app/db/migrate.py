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

from app.db.scram import verifier_for

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
GRANTS = Path(__file__).resolve().parent / "grants.sql"
RUNTIME_ROLE = "mail_triage_runtime"  # fixed: grants.sql names it
# Not the agent's single-replica lock: the old agent, still running while the job of a new release migrates, holds that.
MIGRATION_LOCK_KEY = 7_265_002


class RuntimeRoleNotSafe(RuntimeError):  # noqa: N818 - reads as a state, not as an error class
    """The runtime role is wider than ADR-0030 allows. The message names the role only, never a password or a URL."""


class SchemaNotReady(RuntimeError):  # noqa: N818 - reads as a state, not as an error class
    """The database is not at the Alembic head this build expects. The message holds revisions only, never a URL."""


def _config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _upgrade(url: str) -> None:
    command.upgrade(_config(url), "head")


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


_SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})


async def _connect(url: str) -> asyncpg.Connection:
    """Connect as the URL says, including its TLS setting (``?ssl=``), which SQLAlchemy would otherwise have handled."""
    parsed = make_url(url)
    options: dict[str, object] = {}
    ssl = parsed.query.get("ssl")
    if ssl is not None:
        if not isinstance(ssl, str) or ssl not in _SSL_MODES:
            raise ValueError(f"the ssl setting of the owner URL must be one of: {', '.join(sorted(_SSL_MODES))}")
        options["ssl"] = ssl
    return await asyncpg.connect(
        host=parsed.host,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.database,
        **options,  # type: ignore[arg-type]
    )


async def _ensure_runtime_role(connection: asyncpg.Connection, password: str) -> None:
    """Create the runtime role, or set its password again, so the secret store stays the single source of it.

    Only the SCRAM-SHA-256 verifier is sent (ADR-0030): the clear password never reaches the server, so it cannot end
    up in the statement log or in ``pg_stat_activity``. The statement is built by the server (``format`` with ``%I``
    and ``%L``), so the verifier is quoted as a literal. The role must not hold any membership; that is checked here.
    """
    exists = await connection.fetchval("select 1 from pg_roles where rolname = $1", RUNTIME_ROLE)
    statement = await connection.fetchval(
        "select format('%s ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
        "NOREPLICATION NOBYPASSRLS', $1::text, $2::text, $3::text)",
        "ALTER" if exists else "CREATE",
        RUNTIME_ROLE,
        verifier_for(password),
    )
    await connection.execute(str(statement))
    memberships = await connection.fetchval(
        "select count(*) from pg_auth_members m join pg_roles r on r.oid = m.member where r.rolname = $1", RUNTIME_ROLE
    )
    if memberships:
        raise RuntimeRoleNotSafe(
            f"role {RUNTIME_ROLE} is a member of another role; revoke the membership and run again"
        )


async def migrate_database(owner_url: str, runtime_password: str) -> None:
    """Migrate as the owner, then make the runtime role and its grants match this build. Safe to run again."""
    lock = await _connect(owner_url)
    try:
        await lock.execute("select pg_advisory_lock($1)", MIGRATION_LOCK_KEY)  # waits for a job that is still running
        await asyncio.to_thread(_upgrade, owner_url)
        async with lock.transaction():
            await _ensure_runtime_role(lock, runtime_password)
            await lock.execute(GRANTS.read_text(encoding="utf-8"))
    finally:
        await lock.close()  # closing the connection also releases the lock
