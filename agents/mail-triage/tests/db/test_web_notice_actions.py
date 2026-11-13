"""U-web-settings-27 (AC-13, AC-27, W-11, ADR-0033): the notice buttons against a real PostgreSQL, as the agent role."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.telegram_inbox import Command
from app.core import settings_text
from app.db.pg_settings_store import PgSettingsStore
from app.db.pg_web_lock import PgWebLock
from app.db.pg_web_notice import PgWebNotice
from app.usecases.web_notice import NoticeToken, WebNotice
from app.usecases.web_notice_actions import WebNoticeActions
from tests.db import test_web_role_grants as roles
from tests.db.test_web_notice import _web_changes_up_to
from tests.usecases.fakes_web_notice import RecordingChat, Tokens
from tests.usecases.test_dispatch import FakeChat

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

AGENT, PASSWORDS = roles.AGENT, roles.PASSWORDS
owner, web, agent = roles.owner, roles.web, roles.agent  # the same fixtures: roles, grants and one login per role
NOW = datetime(2026, 11, 11, 13, 5, tzinfo=UTC)
OWNER_ID = "42"
CHAT = 1


class Rig:
    """The real stores on the agent role, the use case that announces and the one that handles the buttons."""

    def __init__(self, engine: AsyncEngine, now: datetime = NOW) -> None:
        sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
        self.notices = PgWebNotice(sessions)
        self.settings = PgSettingsStore(sessions)
        self.chat = FakeChat()
        self.now = now
        self.actions = WebNoticeActions(
            self.notices, PgWebLock(sessions), self.settings, self.chat, chat_id=CHAT, by=OWNER_ID, now=lambda: self.now
        )

    async def announce(self) -> None:
        await WebNotice(self.notices, RecordingChat(), Tokens()).run(NOW)

    async def tap(self, action: str, token: str, chat_id: int = CHAT) -> None:
        await self.actions.on_button(Command("button", f"{action}:{token}", chat_id, 9, "cb", 1), action, token)


@pytest.fixture
async def agent_engine(agent: asyncpg.Connection, migrated_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine that logs in as the real agent role, not the owner."""
    url = make_url(migrated_url).set(username=AGENT, password=PASSWORDS[AGENT])
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


async def _burst_3_4_5(web: asyncpg.Connection, engine: AsyncEngine) -> Rig:
    """Web changes 1 to 5; 1 and 2 were announced before, so the burst is 3, 4 and 5."""
    await _web_changes_up_to(web, 5)
    rig = Rig(engine)
    await rig.notices.advance(2)
    await rig.announce()
    return rig


async def _token(owner: asyncpg.Connection, version: int) -> str:
    return str(await owner.fetchval("select token from web_notice_token where version = $1", version))


async def test_given_a_burst_when_undo_of_notice_5_is_tapped_as_the_agent_role_then_the_values_before_change_3_are_back(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)

    await rig.tap("webundo", await _token(owner, 5))

    row = await owner.fetchrow("select quiet_start, version, updated_via, updated_by from settings.schedule")
    assert row is not None
    assert (row["quiet_start"], row["version"], row["updated_via"], row["updated_by"]) == (602, 6, "telegram", OWNER_ID)
    audit = await owner.fetch("select db_role, via from settings.settings_change order by at, (new->>'version')::int")
    assert [(r["db_role"], r["via"]) for r in audit][-1] == (AGENT, "telegram")
    assert len(audit) == 6  # five web changes and exactly one for the Undo
    assert await owner.fetchval("select count(*) from web_notice_token where version = 5") == 0  # used
    assert rig.chat.edited == [(9, settings_text.WEB_UNDONE)]


async def test_given_a_burst_when_undo_of_notice_3_is_tapped_then_the_result_is_the_same(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)

    await rig.tap("webundo", await _token(owner, 3))

    assert await owner.fetchval("select quiet_start from settings.schedule") == 602
    assert await owner.fetchval("select version from settings.schedule") == 6


async def test_given_telegram_changed_the_row_after_the_burst_when_undo_is_tapped_then_nothing_changes(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)
    await agent.execute(
        "update settings.schedule set quiet_start = 700, version = 6, updated_via = 'telegram', updated_by = '42'"
    )

    await rig.tap("webundo", await _token(owner, 5))

    assert await owner.fetchval("select quiet_start from settings.schedule") == 700
    assert await owner.fetchval("select count(*) from settings.settings_change") == 6  # no record for the refused Undo
    assert rig.chat.edited == [(9, settings_text.UNDO_CHANGED)]


async def test_given_undo_and_lock_when_the_undo_conflicts_then_the_lock_row_is_set_anyway(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)
    await agent.execute(
        "update settings.schedule set quiet_start = 700, version = 6, updated_via = 'telegram', updated_by = '42'"
    )

    await rig.tap("weblock", await _token(owner, 5))

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1
    assert await owner.fetchval("select locked_at from web_auth.web_lock") == NOW
    assert await owner.fetchval("select quiet_start from settings.schedule") == 700
    assert rig.chat.edited == [(9, settings_text.web_locked(settings_text.UNDO_CHANGED))]


async def test_given_undo_and_lock_tapped_twice_when_handled_then_one_lock_row_and_one_undo(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)
    token = await _token(owner, 5)

    await rig.tap("weblock", token)
    await rig.tap("weblock", token)

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1
    assert await owner.fetchval("select version from settings.schedule") == 6
    assert await owner.fetchval("select count(*) from settings.settings_change where db_role = $1", AGENT) == 1
    assert rig.chat.edited[1] == (9, settings_text.WEB_DONE)


async def test_given_a_lock_when_web_unlock_is_sent_then_the_row_is_deleted_and_said(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)
    await rig.tap("weblock", await _token(owner, 4))
    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1

    await rig.actions.unlock(Command("text", "/web_unlock", CHAT, 10, None, 2))
    await rig.actions.unlock(Command("text", "/web_unlock", CHAT, 11, None, 3))

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 0
    assert rig.chat.said == [settings_text.WEB_UNLOCKED, settings_text.WEB_NOT_LOCKED]


async def test_given_a_stranger_chat_when_it_taps_or_unlocks_then_the_database_is_untouched(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)
    await owner.execute("insert into web_auth.web_lock (id, locked_at) values (1, now())")

    await rig.tap("weblock", await _token(owner, 5), chat_id=2)
    await rig.actions.unlock(Command("text", "/web_unlock", 2, 10, None, 2))

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1
    assert await owner.fetchval("select version from settings.schedule") == 5
    assert await owner.fetchval("select count(*) from web_notice_token") == 3
    assert (rig.chat.said, rig.chat.edited) == ([], [])


async def test_given_an_expired_token_when_tapped_as_the_agent_role_then_expired_and_nothing_is_written(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)
    rig.now = NOW + timedelta(hours=24)

    await rig.tap("weblock", await _token(owner, 5))

    assert rig.chat.edited == [(9, settings_text.WEB_EXPIRED)]
    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 0
    assert await owner.fetchval("select version from settings.schedule") == 5


async def test_given_the_agent_role_when_the_lock_and_the_undo_run_then_no_other_web_auth_table_is_touched(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    rig = await _burst_3_4_5(web, agent_engine)

    await rig.tap("weblock", await _token(owner, 5))

    assert await owner.fetchval("select version from settings.schedule") == 6
    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1
    for table in ("session", "login_request", "security_event"):
        assert await owner.fetchval(f"select count(*) from web_auth.{table}") == 0
        assert not await owner.fetchval(
            "select has_table_privilege($1, $2, 'select, insert, update, delete')", AGENT, f"web_auth.{table}"
        )


async def test_given_the_first_saved_row_when_undo_is_tapped_then_nothing_is_written(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    token = NoticeToken("T" * 22, 1, {}, NOW, NOW + timedelta(hours=1), "B" * 22, 1)
    await _web_changes_up_to(web, 1)
    rig = Rig(agent_engine)
    await rig.notices.record_token(token)

    await rig.tap("webundo", token.token)

    assert rig.chat.edited == [(9, settings_text.NOTHING_TO_UNDO)]
    assert await owner.fetchval("select version from settings.schedule") == 1


async def test_given_the_lock_store_when_the_lock_is_set_twice_and_cleared_twice_then_one_row_and_a_true_then_a_false(
    owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(agent_engine, expire_on_commit=False)
    lock = PgWebLock(sessions)

    await lock.lock(NOW)
    await lock.lock(NOW + timedelta(hours=1))  # setting it again changes nothing, not even the time

    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 1
    assert await owner.fetchval("select locked_at from web_auth.web_lock") == NOW
    assert await lock.unlock() is True
    assert await lock.unlock() is False
    assert await owner.fetchval("select count(*) from web_auth.web_lock") == 0
