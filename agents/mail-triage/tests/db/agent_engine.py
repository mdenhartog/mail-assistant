"""One engine whose every connection acts as the agent role, shared by the database tests that test the grants."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.db.conftest import AGENT_ROLE


def create_agent_engine(url: str) -> AsyncEngine:
    """An engine whose connections act as the agent role: the grants are part of what is tested."""
    engine = create_async_engine(url, pool_size=1, max_overflow=0)

    @event.listens_for(engine.sync_engine, "connect")
    def _act_as_agent(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET SESSION AUTHORIZATION "{AGENT_ROLE}"')
        cursor.close()

    return engine
