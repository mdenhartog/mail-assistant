"""U-web-settings-55 (W-13, RT-07, SEC-03): 15 wrong codes set the web lock as the real agent role, once."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.pg_security_events import PgSecurityEvents
from app.db.pg_web_lock import PgWebLock
from app.usecases.code_alert import CodeAlert
from tests.db import test_web_role_grants as roles
from tests.usecases.fakes_code_alert import SpyChat

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

AGENT, PASSWORDS = roles.AGENT, roles.PASSWORDS
owner, agent = roles.owner, roles.agent  # the same fixtures: roles, grants and one login per role
NOW = datetime(2026, 11, 13, 14, 5, tzinfo=UTC)
CLIENT = "CANARYDIGEST" + "0" * 52
USER = "CANARYUSER" + "0" * 54


@pytest.fixture
async def agent_engine(agent: asyncpg.Connection, migrated_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine that logs in as the real agent role, not the owner."""
    url = make_url(migrated_url).set(username=AGENT, password=PASSWORDS[AGENT])
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


class Rig:
    """The use case over the real stores on the agent role."""

    def __init__(self, engine: AsyncEngine) -> None:
        sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
        self.lock = PgWebLock(sessions)
        self.chat = SpyChat()
        self.alert = CodeAlert(PgSecurityEvents(sessions), self.lock, self.chat)


_window = iter(range(1, 10_000))


async def _event(owner: asyncpg.Connection, ago: timedelta, count: int = 1, kind: str = "code_refused") -> None:
    await owner.execute(
        'insert into web_auth.security_event (at, kind, result, username_hash, request_id, client_key, "window", '
        "count) values ($1, $2, 'refused', $3, 'req', $4, $5, $6)",
        NOW - ago,
        kind,
        USER,
        CLIENT,
        next(_window),
        count,
    )


async def test_given_15_wrong_codes_in_24_hours_when_the_agent_runs_then_the_lock_row_is_set_once_with_one_notice(
    owner: asyncpg.Connection, agent_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    for hour in range(5):
        await _event(owner, timedelta(hours=hour * 4, minutes=1), count=3)  # five rows of 3: 15 wrong codes
    rig = Rig(agent_engine)
    caplog.set_level(logging.DEBUG)

    await rig.alert.run(NOW)
    await rig.alert.run(NOW + timedelta(minutes=5))

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1
    assert await owner.fetchval("select locked_at from web_auth.web_lock") == NOW
    assert len(rig.chat.said) == 1
    assert "15 wrong" in rig.chat.said[0]
    assert "/web_unlock" in rig.chat.said[0]
    seen = caplog.text + rig.chat.said[0]
    for canary in ("CANARYDIGEST", "CANARYUSER", CLIENT, USER):
        assert canary not in seen


async def test_given_50_code_invalid_events_when_the_agent_runs_then_no_notice_and_no_lock(
    owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    # U-web-settings-63 (SEC2-01): garbage posts without a live login request are recorded, never counted
    for minute in range(50):
        await _event(owner, timedelta(minutes=minute % 9, seconds=minute), kind="code_invalid")
    await _event(owner, timedelta(minutes=1), count=4)  # four real wrong codes: still below every line
    rig = Rig(agent_engine)

    await rig.alert.run(NOW)

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 0
    assert rig.chat.said == []


async def test_given_14_wrong_codes_and_15_over_24_hours_1_second_when_the_agent_runs_then_nothing_changes(
    owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await _event(owner, timedelta(hours=24, seconds=1))  # out
    await _event(owner, timedelta(hours=24))  # exactly 24 hours: out
    await _event(owner, timedelta(hours=10), count=14)
    rig = Rig(agent_engine)

    await rig.alert.run(NOW)

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 0
    assert rig.chat.said == []


async def test_given_an_unlock_when_the_agent_runs_then_old_events_do_not_lock_again_but_new_ones_do(
    owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await _event(owner, timedelta(hours=2), count=15)
    rig = Rig(agent_engine)
    await rig.alert.run(NOW)
    assert await rig.lock.unlock() is True

    await rig.alert.run(NOW + timedelta(minutes=1))
    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 0

    await _event(owner, timedelta(0), count=15)  # a later row, so a later id
    await rig.alert.run(NOW + timedelta(minutes=2))

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1
    assert len(rig.chat.said) == 2


async def test_given_the_agent_role_when_the_lock_is_set_and_read_then_it_works_and_events_stay_read_only(
    owner: asyncpg.Connection, agent: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = Rig(agent_engine)

    assert await rig.lock.lock(NOW) is True
    assert await rig.lock.is_locked() is True

    assert await owner.fetchval("select has_table_privilege($1, 'web_auth.web_lock', 'select, insert, delete')", AGENT)
    assert not await owner.fetchval(
        "select has_table_privilege($1, 'web_auth.security_event', 'insert, update, delete, truncate')", AGENT
    )
    assert await agent.fetchval("select count(*) from web_auth.security_event") == 0
