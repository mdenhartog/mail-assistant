"""U-mail-categories-23 (AC-31, AC-48, ADR-0033, ADR-0046): the list notice and its buttons on PostgreSQL.

Every test acts as the real agent role (``SET SESSION AUTHORIZATION``), so the grants are part of what is tested; the
web role writes the changes that are announced.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapters.telegram_inbox import Command
from app.core import list_text
from app.db.pg_list_notice import PgActionStore, PgListNoticeStore
from app.db.pg_web_lock import PgWebLock
from app.usecases.list_notice import ListNotice, ListNoticeActions
from app.usecases.telegram_actions import Redeemed, Refusal, TelegramActions
from tests.db.agent_engine import create_agent_engine
from tests.db.conftest import AGENT_ROLE, write_list
from tests.list_notice_support import CHAT, LATER, Nonces, RecordingChat

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

MAILBOX = "mb1"
AGENT_DIGEST = hashlib.sha256(AGENT_ROLE.encode()).hexdigest()


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine whose connections act as the agent role."""
    created = create_agent_engine(cat_url)
    yield created
    await created.dispose()


@dataclass
class Rig:
    """The notice, its buttons and the real stores, on one chat double."""

    store: PgListNoticeStore
    actions: TelegramActions
    chat: RecordingChat
    notice: ListNotice
    buttons: ListNoticeActions

    async def press(self, data: str, *, message_id: int = 7) -> None:
        split = list_text.split_button(data)
        assert split is not None
        await self.buttons.on_button(Command("button", data, CHAT, message_id, "cb", 1), *split)

    def data(self, label: str) -> str:
        return next(b.data for b in self.chat.sent[-1].buttons if b.label == label)


@pytest.fixture
def rig(engine: AsyncEngine) -> Rig:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = PgListNoticeStore(sessions, MAILBOX)
    actions = TelegramActions(PgActionStore(sessions, MAILBOX), Nonces())
    chat = RecordingChat()
    return Rig(
        store,
        actions,
        chat,
        ListNotice(store, chat, actions, chat_id=CHAT),
        ListNoticeActions(actions, store, PgWebLock(sessions), chat, chat_id=CHAT, now=lambda: LATER),
    )


async def _seeded(agent: asyncpg.Connection, rig: Rig) -> None:
    """Version 1 is the agent's own seed (never announced); the cursor sits on it."""
    await write_list(agent, MAILBOX, 1, ["Bills", "Travel"])
    await rig.store.advance(1)


async def test_given_a_web_change_at_night_when_a_cycle_runs_then_one_notice_is_sent_and_the_cursor_advances_after(
    rig: Rig, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await _seeded(cat_agent, rig)
    await write_list(cat_api, MAILBOX, 2, ["Bills", "Travel", "Receipts"])

    await rig.notice.run(LATER)
    await rig.notice.run(LATER)  # the next cycle has nothing new

    (message,) = rig.chat.sent
    assert [b.label for b in message.buttons] == [list_text.UNDO_LABEL, list_text.LOCK_LABEL]
    assert "Receipts" in message.text
    assert await cat_owner.fetchval("select list_notice_version from poll_state") == 2
    rows = await cat_owner.fetch("select kind, target, nonce_hash from categories.telegram_action order by kind")
    assert [(r["kind"], r["target"]) for r in rows] == [("lock", "2-2"), ("undo", "2-2")]
    nonce = message.buttons[0].data.split(":")[1]
    assert nonce not in "".join(r["nonce_hash"] for r in rows)  # only the hash is stored


async def test_given_a_failed_send_when_a_cycle_runs_then_the_cursor_stays_and_the_next_cycle_sends_again(
    rig: Rig, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await _seeded(cat_agent, rig)
    await write_list(cat_api, MAILBOX, 2, ["Bills"])
    rig.chat.fail_send = True

    with pytest.raises(RuntimeError):
        await rig.notice.run(LATER)

    assert await cat_owner.fetchval("select list_notice_version from poll_state") == 1
    rig.chat.fail_send = False
    await rig.notice.run(LATER)
    assert len(rig.chat.sent) == 1
    assert await cat_owner.fetchval("select list_notice_version from poll_state") == 2


async def test_given_a_nonce_when_it_is_pressed_twice_at_once_then_one_wins_and_the_other_sees_already_done(
    rig: Rig, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await _seeded(cat_agent, rig)
    await write_list(cat_api, MAILBOX, 2, ["Bills"])
    await rig.notice.run(LATER)
    data = rig.data(list_text.UNDO_LABEL)

    await asyncio.gather(rig.press(data, message_id=7), rig.press(data, message_id=8))

    answers = [text for _id, text in rig.chat.edits]
    assert len(answers) == 2
    assert answers.count(list_text.ALREADY_DONE) == 1
    assert next(a for a in answers if a != list_text.ALREADY_DONE).startswith("Undone.")
    assert await cat_owner.fetchval("select max(version) from categories.list_version") == 3  # one restore, not two


async def test_given_a_nonce_when_it_is_used_for_the_other_kind_or_another_chat_then_it_is_refused_and_stays_valid(
    rig: Rig, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await _seeded(cat_agent, rig)
    await write_list(cat_api, MAILBOX, 2, ["Bills"])
    await rig.notice.run(LATER)
    undo_nonce = rig.data(list_text.UNDO_LABEL).split(":")[1]

    assert await rig.actions.redeem(undo_nonce, "lock", CHAT, LATER) is Refusal.DONE
    assert await rig.actions.redeem(undo_nonce, "undo", 999, LATER) is Refusal.OTHER_CHAT
    assert await rig.actions.redeem(undo_nonce, "undo", CHAT, LATER) == Redeemed("2-2")


async def test_given_undo_when_the_burst_is_no_longer_the_latest_then_it_is_refused_and_nothing_is_written(
    rig: Rig, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await _seeded(cat_agent, rig)
    await write_list(cat_api, MAILBOX, 2, ["Bills", "Receipts"])
    await rig.notice.run(LATER)
    await write_list(cat_api, MAILBOX, 3, ["Bills", "Receipts", "Fun"])  # after the notice

    await rig.press(rig.data(list_text.UNDO_LABEL))

    assert rig.chat.edits == [(7, list_text.CHANGED_SINCE)]
    assert await cat_owner.fetchval("select max(version) from categories.list_version") == 3
    assert await cat_owner.fetchval("select count(*) from categories.list_audit") == 3


async def test_given_undo_when_it_runs_then_the_restore_is_a_new_version_with_the_old_ids_and_the_database_derives_who(
    rig: Rig, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await _seeded(cat_agent, rig)
    columns = "select id, name, description, position from categories.category where version = $1 order by position"
    original = await cat_owner.fetch(columns, 1)
    await write_list(cat_api, MAILBOX, 2, ["Receipts"])
    await rig.notice.run(LATER)

    await rig.press(rig.data(list_text.UNDO_LABEL))

    restored = await cat_owner.fetch(columns, 3)
    assert [tuple(r) for r in restored] == [tuple(r) for r in original]  # the same ids, names and order
    version = await cat_owner.fetchrow("select created_via, created_by from categories.list_version where version = 3")
    audit = await cat_owner.fetchrow("select channel, actor_digest from categories.list_audit where version = 3")
    assert version is not None
    assert audit is not None
    assert (version["created_via"], version["created_by"]) == ("telegram", AGENT_DIGEST)
    assert (audit["channel"], audit["actor_digest"]) == ("telegram", AGENT_DIGEST)
    assert rig.chat.edits[-1][1].startswith("Undone.")
    # the agent's own Undo is never announced again, but the cursor passes it
    await rig.notice.run(LATER)
    assert len(rig.chat.sent) == 1
    assert await cat_owner.fetchval("select list_notice_version from poll_state") == 3


async def test_given_undo_and_lock_when_the_lock_button_is_pressed_then_the_lock_row_exists_and_the_list_is_back(
    rig: Rig, cat_agent: asyncpg.Connection, cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await _seeded(cat_agent, rig)
    await write_list(cat_api, MAILBOX, 2, ["Receipts"])
    await rig.notice.run(LATER)

    await rig.press(rig.data(list_text.LOCK_LABEL))

    assert await cat_owner.fetchval("select count(*) from web_auth.web_lock") == 1
    assert await cat_owner.fetchval("select max(version) from categories.list_version") == 3


async def test_given_two_restores_at_once_when_both_expect_the_same_version_then_one_wins_and_one_sees_the_change(
    rig: Rig, cat_agent: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_agent, MAILBOX, 1, ["Bills"])
    await write_list(cat_agent, MAILBOX, 2, ["Travel"])
    change = await rig.store.change(2)
    assert change is not None

    results = await asyncio.gather(
        rig.store.restore(change.old, 2), rig.store.restore(change.old, 2), return_exceptions=True
    )

    assert sorted(type(r).__name__ for r in results) == ["ListChanged", "int"]
    assert await cat_owner.fetchval("select max(version) from categories.list_version") == 3


async def test_given_the_agent_role_then_it_can_neither_update_nor_delete_audit_rows_nor_forge_who_wrote(
    cat_agent: asyncpg.Connection,
) -> None:
    await write_list(cat_agent, MAILBOX, 1, ["Bills"])

    for statement in (
        "update categories.list_audit set channel = 'web'",
        "delete from categories.list_audit",
        "insert into categories.list_audit (mailbox_id, version, old_list, new_list, channel, actor_digest) "
        "values ('mb1', 9, '[]', '[]', 'web', 'x')",
        "insert into categories.list_version (mailbox_id, version, created_via) values ('mb1', 2, 'web')",
        "delete from categories.telegram_action",
        "update categories.telegram_action set chat_id = 1",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await cat_agent.execute(statement)
