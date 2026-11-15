"""The shared agent engine really acts as the agent role on every checkout, also after the pool recycled the connection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
import pytest
from sqlalchemy import text

from tests.db.agent_engine import create_agent_engine
from tests.db.conftest import AGENT_ROLE

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    created = create_agent_engine(cat_url)
    yield created
    await created.dispose()


async def _who(engine: AsyncEngine) -> tuple[str, str]:
    async with engine.connect() as connection:
        row = (await connection.execute(text("select current_user, session_user"))).one()
    return row[0], row[1]


async def test_given_the_agent_engine_when_a_connection_is_reused_then_every_checkout_is_the_agent(
    engine: AsyncEngine,
) -> None:
    first = await _who(engine)
    second = await _who(engine)  # pool_size 1: the same connection, reset on checkin
    third = await _who(engine)

    assert first == second == third == (AGENT_ROLE, AGENT_ROLE)


async def test_given_the_agent_engine_when_a_connection_is_reused_then_a_statement_the_agent_is_refused_stays_refused(
    engine: AsyncEngine,
) -> None:
    for _ in range(3):
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|must be owner|must be superuser") as refused:
                await connection.execute(text("create role should_not_exist"))
            assert isinstance(refused.value.__cause__, asyncpg.PostgresError) or refused.value is not None
