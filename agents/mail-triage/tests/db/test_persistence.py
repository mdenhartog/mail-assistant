"""U-09: state in PostgreSQL (AC-12, AC-20, AC-22; design "Data model")."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.models import AuditLog, Base
from app.db.repos import consume_draft, digest_of, record_audit, release_lock, save_draft, try_claim, try_lock
from tests.db.conftest import alembic_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


async def test_given_the_migration_when_upgraded_downgraded_and_upgraded_then_each_step_succeeds_and_matches_the_models(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "head")
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        differences = await connection.run_sync(
            lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
        )
    await engine.dispose()

    assert differences == []


async def test_given_the_same_gmail_message_id_twice_when_claimed_then_only_the_first_succeeds(
    engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions.begin() as session:
        first = await try_claim(session, "18c3f2a", "t1")
    async with sessions.begin() as session:
        second = await try_claim(session, "18c3f2a", "t1")
        other = await try_claim(session, "18c3f2b", "t2")

    assert (first, second, other) == (True, False, True)


async def test_given_two_connections_when_both_take_the_lock_then_only_one_holds_it_until_released(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as one, engine.connect() as two:
        assert await try_lock(one) is True
        assert await try_lock(two) is False
        await release_lock(one)
        assert await try_lock(two) is True
        await release_lock(two)


async def test_given_an_audit_entry_when_written_then_it_stores_ids_and_hashes_and_the_schema_has_no_body_column(
    engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    digest = digest_of("anna@example.com", "Re: Dinner?", "Yes, Friday.")

    async with sessions.begin() as session:
        await record_audit(session, "send", ref="d-1", digest=digest, detail="confirmed", at=NOW)
    async with sessions.begin() as session:
        stored = (await session.execute(text("select kind, ref, digest, detail from audit_log"))).one()

    assert tuple(stored) == ("send", "d-1", digest, "confirmed")
    columns = {column.name for column in AuditLog.__table__.columns}
    assert not columns & {"body", "text", "content", "message", "snippet", "subject"}


async def test_given_a_stored_draft_when_consumed_then_it_works_once_and_never_again(engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    digest = digest_of("anna@example.com", "Re: Dinner?", "Yes, Friday.")
    async with sessions.begin() as session:
        await save_draft(
            session,
            "d-1",
            alert_id=None,
            recipient="anna@example.com",
            body="Yes, Friday.",
            digest=digest,
            expires_at=NOW + timedelta(minutes=30),
        )

    async with sessions.begin() as session:
        first = await consume_draft(session, "d-1", digest, now=NOW)
    async with sessions.begin() as session:
        second = await consume_draft(session, "d-1", digest, now=NOW)

    assert first is not None
    assert first.body == "Yes, Friday."
    assert second is None


@pytest.mark.parametrize(
    ("digest", "when"),
    [("0" * 64, NOW), (None, NOW + timedelta(minutes=31))],  # wrong digest; expired
)
async def test_given_a_wrong_digest_or_an_expired_draft_when_consumed_then_nothing_is_returned_and_it_stays_unused(
    engine: AsyncEngine, digest: str | None, when: datetime
) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    real = digest_of("anna@example.com", "Re: Dinner?", "Yes, Friday.")
    async with sessions.begin() as session:
        await save_draft(
            session,
            "d-2",
            alert_id=None,
            recipient=None,
            body="Yes, Friday.",
            digest=real,
            expires_at=NOW + timedelta(minutes=30),
        )

    async with sessions.begin() as session:
        refused = await consume_draft(session, "d-2", digest or real, now=when)
    async with sessions.begin() as session:
        still_there = await consume_draft(session, "d-2", real, now=NOW)

    assert refused is None
    assert still_there is not None


def test_given_a_changed_field_when_digested_then_the_digest_changes() -> None:
    base = digest_of("a@example.com", "Subject", "Body")

    assert len(base) == 64
    assert base != digest_of("b@example.com", "Subject", "Body")
    assert base != digest_of("a@example.com", "Subject 2", "Body")
    assert base != digest_of("a@example.com", "Subject", "Body 2")
    assert digest_of("a@example.com", "Sub", "jectBody") != base  # field boundaries count
