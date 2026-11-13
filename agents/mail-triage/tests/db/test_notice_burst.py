"""U-web-settings-56 (AC-13, CR-07, ADR-0033): an Undo burst is found by its own id, against a real PostgreSQL."""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import settings_text
from app.usecases.web_notice import WebNotice
from tests.db import test_web_role_grants as roles
from tests.db.test_web_notice import _FIRST, ACTOR
from tests.db.test_web_notice_actions import Rig
from tests.usecases.fakes_web_notice import RecordingChat, Tokens

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncEngine

AGENT, PASSWORDS = roles.AGENT, roles.PASSWORDS
owner, web, agent = roles.owner, roles.web, roles.agent  # the same fixtures: roles, grants and one login per role


@pytest.fixture
async def agent_engine(agent: asyncpg.Connection, migrated_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine that logs in as the real agent role, not the owner."""
    url = make_url(migrated_url).set(username=AGENT, password=PASSWORDS[AGENT])
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


async def _web_change(web: asyncpg.Connection, version: int, quiet_start: int) -> None:
    await web.execute(
        f"update settings.schedule set quiet_start = {quiet_start}, version = {version}, "
        f"updated_via = 'web', updated_by = '{ACTOR}'"
    )


async def _token(owner: asyncpg.Connection, version: int) -> str:
    """The first token recorded for ``version`` (a retry may record a second one)."""
    return str(
        await owner.fetchval(
            "select token from web_notice_token where version = $1 order by created_at, token", version
        )
    )


async def test_given_two_bursts_with_equal_before_values_when_undo_of_the_older_is_tapped_then_it_is_refused_as_changed(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await web.execute(_FIRST)  # version 1, quiet start 600
    rig, tokens, chat = Rig(agent_engine), Tokens(), RecordingChat()
    await rig.notices.advance(1)
    await _web_change(web, 2, 650)
    await _web_change(web, 3, 600)  # burst A is versions 2 and 3; it restores quiet start 600
    await WebNotice(rig.notices, chat, tokens).run(rig.now)
    await _web_change(web, 4, 700)
    await _web_change(web, 5, 701)  # burst B is versions 4 and 5; its first change started from 600 as well
    await WebNotice(rig.notices, chat, tokens).run(rig.now)

    await rig.tap("webundo", await _token(owner, 2))

    assert await owner.fetchval("select version from settings.schedule") == 5  # burst A ends at version 3
    assert await owner.fetchval("select quiet_start from settings.schedule") == 701
    assert rig.chat.edited == [(9, settings_text.UNDO_CHANGED)]


async def test_given_two_bursts_with_equal_before_values_when_undo_of_the_newer_is_tapped_then_only_it_is_restored(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await web.execute(_FIRST)
    rig, tokens, chat = Rig(agent_engine), Tokens(), RecordingChat()
    await rig.notices.advance(1)
    await _web_change(web, 2, 650)
    await _web_change(web, 3, 600)
    await WebNotice(rig.notices, chat, tokens).run(rig.now)
    await _web_change(web, 4, 700)
    await _web_change(web, 5, 701)
    await WebNotice(rig.notices, chat, tokens).run(rig.now)

    await rig.tap("webundo", await _token(owner, 4))

    assert await owner.fetchval("select quiet_start from settings.schedule") == 600  # before burst B, which is 600
    assert await owner.fetchval("select version from settings.schedule") == 6
    assert rig.chat.edited == [(9, settings_text.WEB_UNDONE)]


async def test_given_a_send_failure_after_the_first_notice_when_retried_then_undo_of_the_first_returns_the_old_values(
    web: asyncpg.Connection, owner: asyncpg.Connection, agent_engine: AsyncEngine
) -> None:
    await web.execute(_FIRST)  # version 1, quiet start 600
    rig, tokens, chat = Rig(agent_engine), Tokens(), RecordingChat()
    await rig.notices.advance(1)
    for version, start in ((2, 650), (3, 660), (4, 670)):
        await _web_change(web, version, start)
    notice = WebNotice(rig.notices, chat, tokens)
    chat.fail_on_text = "change 3"  # the first notice goes out, the second does not

    with pytest.raises(RuntimeError):
        await notice.run(rig.now)
    await notice.run(rig.now)  # the retry sends notices 3 and 4
    await rig.tap("webundo", await _token(owner, 2))

    assert await owner.fetchval("select quiet_start from settings.schedule") == 600  # before change 2, not before 3
    assert await owner.fetchval("select version from settings.schedule") == 5
    assert rig.chat.edited == [(9, settings_text.WEB_UNDONE)]
