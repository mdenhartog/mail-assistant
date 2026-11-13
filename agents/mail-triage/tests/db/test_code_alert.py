"""U-web-settings-48 (AC-20, W-13, W-15, SEC-04): the wrong-code alert against a real PostgreSQL, as the agent role."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.pg_security_events import PgSecurityEvents
from app.usecases.code_alert import CodeAlert
from tests.db import test_web_role_grants as roles
from tests.usecases.fakes_code_alert import SpyChat

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

AGENT, PASSWORDS = roles.AGENT, roles.PASSWORDS
owner, agent = roles.owner, roles.agent  # the same fixtures: roles, grants and one login per role
NOW = datetime(2026, 11, 13, 14, 5, tzinfo=UTC)
CLIENT = "CANARYDIGEST" + "0" * 52  # a digest-shaped client key that must never reach a notice or a log
USER = "CANARYUSER" + "0" * 54


@pytest.fixture
async def agent_engine(agent: asyncpg.Connection, migrated_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine that logs in as the real agent role, not the owner."""
    url = make_url(migrated_url).set(username=AGENT, password=PASSWORDS[AGENT])
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


def _events(engine: AsyncEngine) -> PgSecurityEvents:
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    return PgSecurityEvents(sessions)


async def _event(
    owner: asyncpg.Connection, ago: timedelta, *, kind: str = "code_refused", count: int = 1, window: int = 0
) -> None:
    result = "refused" if kind in {"code_refused", "code_request_refused", "csrf_refused"} else "failed"
    await owner.execute(
        'insert into web_auth.security_event (at, kind, result, username_hash, request_id, client_key, "window", '
        "count) "
        "values ($1, $2, $3, $4, 'req', $5, $6, $7)",
        NOW - ago,
        kind,
        result,
        USER,
        CLIENT,
        window,
        count,
    )


# ---- criterion 5: the real agent role -----


async def test_given_the_agent_role_when_it_selects_security_events_then_it_works(
    owner: asyncpg.Connection, agent: asyncpg.Connection
) -> None:
    await _event(owner, timedelta(minutes=1), count=3)

    assert await agent.fetchval("select sum(count) from web_auth.security_event") == 3


@pytest.mark.parametrize(
    "statement",
    [
        'insert into web_auth.security_event (kind, result, request_id, client_key, "window") '
        "values ('code_refused', 'refused', 'r', 'k', 1)",
        "update web_auth.security_event set count = 99",
        "delete from web_auth.security_event",
        "truncate web_auth.security_event",
        "select count(*) from web_auth.session",
        "update web_auth.session set last_seen_at = now()",
        "select count(*) from web_auth.login_request",
        "update web_auth.login_request set attempts = 0",
        "delete from web_auth.login_request",
    ],
)
async def test_given_the_agent_role_when_it_writes_events_or_touches_session_and_login_request_then_42501(
    owner: asyncpg.Connection, agent: asyncpg.Connection, statement: str
) -> None:
    await _event(owner, timedelta(minutes=1))

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await agent.execute(statement)


async def test_given_the_agent_role_when_it_updates_event_columns_then_postgres_refuses_each(
    owner: asyncpg.Connection, agent: asyncpg.Connection
) -> None:
    await _event(owner, timedelta(minutes=1))

    for column in ("count = 1", "kind = 'rate_limited'", "client_key = repeat('e', 64)"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await agent.execute(f"update web_auth.security_event set {column}")


# ---- criteria 1 to 4 and 6 against the real store -----


async def test_given_one_row_with_count_5_when_the_agent_runs_then_one_notice_with_the_sum(
    owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await _event(owner, timedelta(seconds=30), count=5)
    chat = SpyChat()

    await CodeAlert(_events(agent_engine), chat).run(NOW)

    assert len(chat.said) == 1
    assert "5 wrong" in chat.said[0]


async def test_given_rows_of_other_kinds_and_old_rows_when_the_agent_runs_then_only_fresh_wrong_codes_count(
    owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await _event(owner, timedelta(minutes=1), count=2, window=1)
    await _event(owner, timedelta(minutes=9, seconds=59), count=2, window=2)  # inside
    await _event(owner, timedelta(minutes=10), count=50, window=3)  # exactly 10 minutes: outside
    await _event(owner, timedelta(minutes=10, seconds=1), count=50, window=4)  # outside
    for kind in ("rate_limited", "csrf_refused", "mail_failed", "code_request_refused"):
        await _event(owner, timedelta(minutes=1), kind=kind, count=50, window=5)
    chat = SpyChat()
    alert = CodeAlert(_events(agent_engine), chat)

    await alert.run(NOW)  # 4 wrong codes count
    assert chat.said == []
    await _event(owner, timedelta(seconds=1), window=6)
    await alert.run(NOW)

    assert len(chat.said) == 1
    assert "5 wrong" in chat.said[0]


async def test_given_events_with_canary_digest_and_username_when_the_agent_runs_then_no_notice_or_log_holds_them(
    owner: asyncpg.Connection, agent_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    await _event(owner, timedelta(seconds=30), count=6)
    chat = SpyChat()
    caplog.set_level(logging.DEBUG)

    await CodeAlert(_events(agent_engine), chat).run(NOW)

    seen = caplog.text + " ".join(chat.said)
    assert chat.said
    for canary in ("CANARYDIGEST", "CANARYUSER", CLIENT, USER):
        assert canary not in seen
