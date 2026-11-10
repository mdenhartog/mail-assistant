"""U-quiet-hours-16d (RT-5): the last handled Telegram update id lives in ``poll_state`` and survives a restart."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic import command
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.pg_conversation import ConversationStore
from app.db.pg_store import PgStore
from app.db.pg_update_cursor import PgUpdateCursor
from app.usecases.dispatch import CommandRouter
from tests.db.conftest import alembic_config
from tests.usecases.fakes_dialogue import FakeSettings
from tests.usecases.test_dispatch import FakeChat, FakeReply, FakeSnooze, FakeStore
from tests.usecases.test_dispatch import text as typed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


def _sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_given_a_fresh_database_when_read_then_no_update_id_is_stored(engine: AsyncEngine) -> None:
    assert await PgUpdateCursor(_sessions(engine)).last() is None


async def test_given_a_stored_id_when_a_new_cursor_reads_it_then_it_is_still_there(engine: AsyncEngine) -> None:
    await PgUpdateCursor(_sessions(engine)).advance(777)

    assert await PgUpdateCursor(_sessions(engine)).last() == 777


async def test_given_a_stored_id_when_an_older_one_is_stored_then_the_id_never_goes_back(engine: AsyncEngine) -> None:
    cursor = PgUpdateCursor(_sessions(engine))
    await cursor.advance(900)

    await cursor.advance(5)

    assert await cursor.last() == 900


async def test_given_telegram_ids_beyond_32_bits_when_stored_then_they_are_kept(engine: AsyncEngine) -> None:
    cursor = PgUpdateCursor(_sessions(engine))

    await cursor.advance(5_000_000_000)

    assert await cursor.last() == 5_000_000_000


async def test_given_the_gmail_position_when_the_update_id_is_stored_then_neither_overwrites_the_other(
    engine: AsyncEngine,
) -> None:
    sessions = _sessions(engine)
    store, cursor = PgStore(sessions, ConversationStore(sessions, lambda: NOW)), PgUpdateCursor(sessions)

    await store.save_history_id("100")
    await cursor.advance(7)
    await store.save_history_id("101")

    assert await store.history_id() == "101"
    assert await cursor.last() == 7


async def test_given_a_restart_when_the_same_update_comes_again_then_the_real_router_ignores_it(
    engine: AsyncEngine,
) -> None:
    sessions = _sessions(engine)

    def router() -> tuple[CommandRouter, FakeChat, FakeSettings]:
        chat, settings = FakeChat(), FakeSettings()
        built = CommandRouter(
            FakeReply(),
            FakeSnooze(),
            FakeStore(),
            chat,
            ConversationStore(sessions, lambda: NOW),
            PgUpdateCursor(sessions),
        )
        built.register(settings)
        return built, chat, settings

    first, _, first_settings = router()
    await first.handle(typed("/settings", update_id=777))
    restarted, _, second_settings = router()
    await restarted.handle(typed("/settings", update_id=777))

    assert len(first_settings.began) == 1
    assert second_settings.began == []
    assert await PgUpdateCursor(sessions).last() == 777


async def test_given_revision_0006_with_a_poll_row_when_upgraded_then_the_row_is_kept_without_an_update_id(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "0006")
    connection = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await connection.execute("insert into poll_state (id, history_id) values (1, '55')")
    finally:
        await connection.close()

    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(database_url)
    try:
        assert await PgStore(_sessions(engine), ConversationStore(_sessions(engine), lambda: NOW)).history_id() == "55"
        assert await PgUpdateCursor(_sessions(engine)).last() is None
    finally:
        await engine.dispose()


async def test_given_revision_0007_when_downgraded_then_the_column_is_gone_and_the_gmail_position_stays(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    await asyncio.to_thread(command.upgrade, config, "head")
    connection = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await connection.execute("insert into poll_state (id, history_id, telegram_update_id) values (1, '55', 9)")

        await asyncio.to_thread(command.downgrade, config, "0006")

        columns = await connection.fetch(
            "select column_name from information_schema.columns where table_name = 'poll_state'"
        )
        assert {r["column_name"] for r in columns} == {"id", "history_id"}
        assert await connection.fetchval("select history_id from poll_state") == "55"
    finally:
        await connection.close()
