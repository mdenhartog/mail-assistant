"""U-quiet-hours-15a: ``serve`` no longer migrates, it verifies the schema; ``migrate`` runs the job (ADR-0025)."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.settings import load_migrate_settings
from app.wiring import EXIT_OK, EXIT_SCHEMA_NOT_READY, migrate, verify_schema

if TYPE_CHECKING:
    import pytest

    from app.settings import MigrateSettings

WIRING = Path(__file__).resolve().parents[2] / "app" / "wiring.py"


def _settings(database_url: str, password: str = "runtime-lifecycle-test-only") -> MigrateSettings:  # noqa: S107
    return load_migrate_settings(
        {
            "DATABASE_OWNER_URL": database_url,
            "RUNTIME_ROLE_PASSWORD": password,
            "WEB_ROLE_PASSWORD": "web-lifecycle-test-only",
            "ENVIRONMENT": "test",  # the test database has no TLS
            "DATABASE_SSL": "disable",
        }
    )


def test_given_the_agent_wiring_when_scanned_then_it_never_imports_or_calls_the_migrations_in_serve() -> None:
    tree = ast.parse(WIRING.read_text(encoding="utf-8"))
    serve = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "serve")

    called = {
        n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
        for n in ast.walk(serve)
        if isinstance(n, ast.Call)
    }
    assert not called & {"upgrade", "migrate", "migrate_database"}
    assert "verify_schema" in called


async def test_given_an_unmigrated_database_when_the_agent_verifies_then_it_exits_non_zero_with_a_clear_message(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    engine = create_async_engine(database_url)
    try:
        with caplog.at_level(logging.ERROR):
            code = await verify_schema(engine)
    finally:
        await engine.dispose()

    assert code == EXIT_SCHEMA_NOT_READY
    assert code != 0
    assert "run the migrate job" in caplog.text
    assert make_url(database_url).password not in caplog.text


async def test_given_the_migrate_command_when_it_runs_then_the_agent_can_start_against_the_result(
    database_url: str,
) -> None:
    assert await migrate(_settings(database_url)) == EXIT_OK

    runtime = make_url(database_url).set(username="mail_triage_runtime", password="runtime-lifecycle-test-only")
    engine = create_async_engine(runtime.render_as_string(hide_password=False))
    try:
        assert await verify_schema(engine) is None
    finally:
        await engine.dispose()
        await _restore_shared_password(database_url)


async def test_given_a_wrong_owner_password_when_migrate_runs_then_it_exits_non_zero_without_the_password(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    broken = make_url(database_url).set(password="wrong-owner-secret").render_as_string(hide_password=False)

    with caplog.at_level(logging.INFO):
        code = await migrate(_settings(broken, "never-applied-secret"))

    assert code not in (0, None)
    assert "wrong-owner-secret" not in caplog.text
    assert "never-applied-secret" not in caplog.text


async def _restore_shared_password(database_url: str) -> None:
    parsed = make_url(database_url)
    connection = await asyncpg.connect(
        host=parsed.host, port=parsed.port, user=parsed.username, password=parsed.password, database=parsed.database
    )
    try:
        await connection.execute("ALTER ROLE mail_triage_runtime PASSWORD 'runtime-test-only'")
    finally:
        await connection.close()
