"""Fixtures for the plan stores on PostgreSQL: every connection acts as the real agent role (``SET SESSION AUTHORIZATION``).

The grants are part of what the tests exercise. The owner connection (``cat_owner``) seeds lists and plans, and the api
role writes what the user does (approvals, move-back requests).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.judgement import OTHER_ID
from tests.db.conftest import AGENT_ROLE, write_list

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

MAILBOX = "mb1"


@pytest.fixture
async def agent_sessions(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[async_sessionmaker[Any]]:
    """Sessions whose connections act as the agent role."""
    engine: AsyncEngine = create_async_engine(cat_url)

    @event.listens_for(engine.sync_engine, "connect")
    def _act_as_agent(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET SESSION AUTHORIZATION "{AGENT_ROLE}"')
        cursor.close()

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed_list(owner: asyncpg.Connection, names: list[str], version: int = 1, mailbox: str = MAILBOX) -> list[str]:
    """Write a list version; return the ids of its categories in position order."""
    await write_list(owner, mailbox, version, names)
    rows = await owner.fetch(
        "select id from categories.category where mailbox_id = $1 and version = $2 order by position", mailbox, version
    )
    return [str(r["id"]) for r in rows]


async def seed_approval(owner: asyncpg.Connection, plan_id: uuid.UUID, channel: str = "web") -> None:
    """The approval record ``approve_plan`` leaves (the owner writes it directly, as the other tests do)."""
    await owner.execute(
        "insert into categories.plan_approval (mailbox_id, plan_id, approved_count, channel, actor_digest) "
        "values ($1, $2, 1, $3, $4)",
        MAILBOX,
        plan_id,
        channel,
        "c" * 64,
    )


__all__ = ["MAILBOX", "OTHER_ID", "agent_sessions", "seed_approval", "seed_list"]
