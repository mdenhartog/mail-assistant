"""U-quiet-hours-16b: ``app.consent`` no longer migrates; it only checks the schema (ADR-0025, SEC-5)."""

from __future__ import annotations

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.consent import ConsentError, require_schema


async def test_given_a_database_without_the_schema_when_consent_starts_then_it_names_the_migrate_job_and_runs_no_ddl(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    try:
        with pytest.raises(ConsentError, match="migrate job"):
            await require_schema(engine)
    finally:
        await engine.dispose()

    connection = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        assert await connection.fetchval("select count(*) from pg_tables where schemaname = 'public'") == 0
    finally:
        await connection.close()


async def test_given_a_migrated_database_when_consent_starts_then_the_schema_check_passes(migrated_url: str) -> None:
    engine = create_async_engine(migrated_url)
    try:
        await require_schema(engine)
    finally:
        await engine.dispose()
