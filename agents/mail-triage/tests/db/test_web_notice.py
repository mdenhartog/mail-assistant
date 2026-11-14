"""U-web-settings-26 (AC-13, W-11, ADR-0033): the notice store against a real PostgreSQL, as the real agent role."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.pg_web_notice import PgWebNotice
from app.usecases.web_notice import NoticeToken, WebNotice
from tests.db import test_web_role_grants as roles
from tests.usecases.fakes_web_notice import RecordingChat, Tokens

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

ACTOR, AGENT, PASSWORDS, WEB = roles.ACTOR, roles.AGENT, roles.PASSWORDS, roles.WEB
owner, web, agent = roles.owner, roles.web, roles.agent  # the same fixtures: roles, grants and one login per role
NOW = datetime(2026, 11, 11, 13, 5, tzinfo=UTC)
_FIRST = (
    "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, updated_by) "
    f"values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', '{ACTOR}')"
)


async def _web_changes_up_to(web: asyncpg.Connection, version: int) -> None:
    """Version 1 is the insert; each further version moves the quiet start by one minute (600 + version)."""
    await web.execute(_FIRST)
    for next_version in range(2, version + 1):
        await web.execute(
            f"update settings.schedule set quiet_start = {600 + next_version}, version = {next_version}, "
            f"updated_via = 'web', updated_by = '{ACTOR}'"
        )


@pytest.fixture
async def agent_engine(agent: asyncpg.Connection, migrated_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine that logs in as the real agent role, not the owner."""
    url = make_url(migrated_url).set(username=AGENT, password=PASSWORDS[AGENT])
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


def _store(engine: AsyncEngine) -> PgWebNotice:
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    return PgWebNotice(sessions)


async def test_given_web_changes_9_10_and_11_when_read_as_the_agent_role_then_they_come_in_numeric_order(
    web: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await _web_changes_up_to(web, 11)

    changes = await _store(agent_engine).pending_after(8)

    assert [c.version for c in changes] == [9, 10, 11]  # as text, "10" would sort before "9"
    assert changes[0].old is not None
    assert changes[0].old.quiet_start == time(10, 8)
    assert changes[0].new.quiet_start == time(10, 9)
    assert changes[0].new.zone == "Europe/Amsterdam"
    assert changes[0].at.tzinfo is not None


async def test_given_the_first_row_when_read_then_the_change_has_no_old_values(
    web: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await _web_changes_up_to(web, 1)

    [change] = await _store(agent_engine).pending_after(0)

    assert change.version == 1
    assert change.old is None


async def test_given_a_telegram_change_when_read_then_it_is_not_a_web_change(
    owner: asyncpg.Connection,
    web: asyncpg.Connection,
    agent: asyncpg.Connection,
    agent_engine: AsyncEngine,
) -> None:
    await _web_changes_up_to(web, 2)
    await agent.execute(
        "update settings.schedule set quiet_start = 700, version = 3, updated_via = 'telegram', updated_by = '42'"
    )

    changes = await _store(agent_engine).pending_after(0)

    assert [c.version for c in changes] == [1, 2]


async def test_given_audit_records_whose_actor_text_lies_when_read_then_the_server_derived_role_decides(
    owner: asyncpg.Connection,
    web: asyncpg.Connection,
    agent_engine: AsyncEngine,
) -> None:
    await _web_changes_up_to(web, 1)
    new = json.dumps(
        {"zone": "Europe/Amsterdam", "quiet_start": 700, "quiet_end": 900, "overview_at": 1080, "remind_at": 540}
        | {"version": 2}
    )
    old = json.dumps(
        {"zone": "Europe/Amsterdam", "quiet_start": 600, "quiet_end": 900, "overview_at": 1080, "remind_at": 540}
        | {"version": 1}
    )
    # A web row whose text claims the agent, and an agent row whose text claims the web.
    insert = (
        "insert into settings.settings_change (at, via, by, db_role, old, new) "
        "values (now(), $1, $2, $3, $4::jsonb, $5::jsonb)"
    )
    await owner.execute(insert, "telegram", AGENT, WEB, old, new)
    await owner.execute(insert, "web", ACTOR, AGENT, old, new.replace('"version": 2', '"version": 3'))

    changes = await _store(agent_engine).pending_after(1)

    assert [c.version for c in changes] == [2]


async def test_given_the_agent_role_when_it_writes_the_cursor_and_the_token_then_both_work_and_persist(
    agent_engine: AsyncEngine, owner: asyncpg.Connection
) -> None:
    store = _store(agent_engine)
    assert await store.last_announced() == 0

    await store.advance(10)
    await store.advance(9)  # the cursor never goes back
    await store.record_token(
        NoticeToken(
            "T" * 22,
            10,
            {"zone": "Europe/Amsterdam", "quiet_start": 600},
            NOW,
            NOW + timedelta(hours=24),
            "B" * 22,
            10,
        )
    )

    assert await store.last_announced() == 10
    row = await owner.fetchrow("select token, version, before, expires_at from web_notice_token")
    assert row is not None
    assert (row["token"], row["version"], json.loads(row["before"])["quiet_start"]) == ("T" * 22, 10, 600)
    assert row["expires_at"] == NOW + timedelta(hours=24)


async def test_given_a_web_change_when_the_use_case_runs_twice_as_the_agent_role_then_one_notice_and_the_cursor_moved(
    web: asyncpg.Connection, agent_engine: AsyncEngine, owner: asyncpg.Connection
) -> None:
    await _web_changes_up_to(web, 3)
    chat = RecordingChat()
    notice = WebNotice(_store(agent_engine), chat, Tokens())

    await notice.run(NOW)
    await notice.run(NOW)

    assert len(chat.sent) == 3
    assert await owner.fetchval("select web_notice_version from poll_state") == 3
    # Undo of every notice goes back to the values before the first change in the burst.
    rows = await owner.fetch("select version, before from web_notice_token order by version")
    assert [r["version"] for r in rows] == [1, 2, 3]
    assert {json.loads(r["before"]).get("quiet_start") for r in rows} == {None}  # the first row replaced nothing


async def test_given_the_poll_state_row_exists_when_the_cursor_advances_then_the_history_and_update_ids_stay(
    agent_engine: AsyncEngine, owner: asyncpg.Connection
) -> None:
    await owner.execute("insert into poll_state (id, history_id, telegram_update_id) values (1, 'h9', 77)")

    await _store(agent_engine).advance(4)

    row = await owner.fetchrow("select history_id, telegram_update_id, web_notice_version from poll_state")
    assert row is not None
    assert (row["history_id"], row["telegram_update_id"], row["web_notice_version"]) == ("h9", 77, 4)


async def test_given_a_web_reset_to_the_defaults_when_the_use_case_runs_then_one_more_notice_follows(
    web: asyncpg.Connection, agent_engine: AsyncEngine, owner: asyncpg.Connection
) -> None:
    """U-web-settings-45 (AC-13): the reset is one more web write of the same row, so the poll sees it as such."""
    await _web_changes_up_to(web, 2)
    chat = RecordingChat()
    notice = WebNotice(_store(agent_engine), chat, Tokens())
    await notice.run(NOW)
    await web.execute(
        "update settings.schedule set zone = 'Europe/Amsterdam', quiet_start = 1380, quiet_end = 420, "
        "overview_at = 1080, remind_at = 540, version = 3, updated_via = 'web', "
        f"updated_by = '{ACTOR}'"
    )

    await notice.run(NOW)

    assert len(chat.sent) == 3
    assert await owner.fetchval("select web_notice_version from poll_state") == 3
    [reset] = await _store(agent_engine).pending_after(2)
    assert reset.new.quiet_start == time(23, 0)
    assert reset.old is not None
    assert reset.old.quiet_start == time(10, 2)
