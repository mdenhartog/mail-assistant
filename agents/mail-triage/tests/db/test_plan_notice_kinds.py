"""RED-001: the button kinds of the plan notice are the kinds ``telegram_action`` allows (ADR-0046, AC-42, AC-48).

The notice stores a nonce per button; a kind the table refuses means the notice is never sent. The contract test
compares the code with the constraint of the migrated database and the model; the end-to-end test sends the notices as
the agent role and redeems each button.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.adapters.telegram_inbox import Command
from app.core import approval_text
from app.db.models import TelegramAction
from app.db.pg_approval import PgApprovalStore, PgMoveBackRequests
from app.db.pg_list_notice import PgActionStore
from app.db.pg_web_lock import PgWebLock
from app.usecases import approval_notice
from app.usecases.approval_notice import ApprovalNotice, PlanNoticeActions
from app.usecases.resort_apply import Offer
from app.usecases.telegram_actions import TelegramActions
from tests.db.resort_support import MAILBOX, agent_sessions
from tests.db.test_pg_approval import delayed
from tests.db.test_pg_resort_apply import scheduled_plan
from tests.list_notice_support import CHAT, Nonces, RecordingChat

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]

LIST_KINDS = {"undo", "lock"}  # the list notice (U-23)
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


def _kinds(definition: str) -> set[str]:
    return set(re.findall(r"'([a-z_]+)'", definition))


async def test_given_the_notice_code_when_compared_with_the_constraint_then_every_kind_is_allowed(
    cat_owner: asyncpg.Connection,
) -> None:
    definition = await cat_owner.fetchval(
        "select pg_get_constraintdef(oid) from pg_constraint where conname = 'ck_telegram_action_kind'"
    )
    model = next(c for c in TelegramAction.__table_args__ if getattr(c, "name", "") == "ck_telegram_action_kind")

    allowed = _kinds(str(definition))

    assert set(approval_notice._KINDS.values()) | LIST_KINDS == allowed  # pyright: ignore[reportPrivateUsage]  # the contract
    assert _kinds(str(model.sqltext)) == allowed  # type: ignore[attr-defined]  # the model says what the database says


async def test_given_a_delayed_plan_when_noticed_then_cancel_and_lock_are_stored_and_redeemable(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    chat = RecordingChat()
    actions = TelegramActions(PgActionStore(agent_sessions, MAILBOX), Nonces())
    store = PgApprovalStore(agent_sessions, MAILBOX)
    plan_id = await delayed(cat_owner)
    await ApprovalNotice(actions, store, chat, chat_id=CHAT).run(NOW)
    handler = PlanNoticeActions(
        actions,
        store,
        PgMoveBackRequests(agent_sessions, MAILBOX),
        PgWebLock(agent_sessions),
        chat,
        chat_id=CHAT,
        now=lambda: NOW,
    )

    kinds = await cat_owner.fetch("select kind, target from categories.telegram_action order by kind")
    assert [(r["kind"], r["target"]) for r in kinds] == [("plan_cancel", str(plan_id)), ("plan_lock", str(plan_id))]

    (message,) = chat.sent
    for button in message.buttons:
        split = approval_text.split_button(button.data)
        assert split is not None
        await handler.on_button(Command("button", button.data, CHAT, 7, "cb", 1), *split)

    assert chat.edits[0][1] == approval_text.CANCELLED
    assert chat.edits[1][1] == approval_text.locked_and_cancelled(0)  # the cancel came first
    assert await cat_owner.fetchval("select count(*) from categories.telegram_action where used_at is null") == 0


async def test_given_an_applied_plan_when_the_result_is_sent_then_move_back_is_stored_and_redeemable(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    chat = RecordingChat()
    actions = TelegramActions(PgActionStore(agent_sessions, MAILBOX), Nonces())
    store = PgApprovalStore(agent_sessions, MAILBOX)
    plan_id = await scheduled_plan(cat_owner, state="applied")
    notice = ApprovalNotice(actions, store, chat, chat_id=CHAT)
    await notice.send_result("done", plan_id, (Offer.MOVE_BACK,), NOW)
    handler = PlanNoticeActions(
        actions,
        store,
        PgMoveBackRequests(agent_sessions, MAILBOX),
        PgWebLock(agent_sessions),
        chat,
        chat_id=CHAT,
        now=lambda: NOW,
    )

    assert await cat_owner.fetchval("select kind from categories.telegram_action") == "plan_move_back"
    (button,) = chat.sent[0].buttons
    split = approval_text.split_button(button.data)
    assert split is not None
    await handler.on_button(Command("button", button.data, CHAT, 7, "cb", 1), *split)

    assert chat.edits[-1][1] == approval_text.MOVE_BACK_ASKED
    assert await cat_owner.fetchval("select count(*) from categories.move_back_request") == 1
