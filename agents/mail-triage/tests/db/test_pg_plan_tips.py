"""U-label-structure-24, criteria 1, 3 and 5 on the real database, as the agent role (ADR-0056, migration 0029)."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.db.pg_resort import PgBuildStore, PgTipStore
from app.usecases.plan_tips import TipRow
from tests.db.resort_support import MAILBOX, OTHER_ID, agent_sessions, seed_list

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]  # the fixture is used by name


async def _plan_with_items(
    owner: asyncpg.Connection, kind: str = "review", state: str = "ready"
) -> tuple[uuid.UUID, str]:
    category = (await seed_list(owner, ["Finance"]))[0]
    plan_id, request_id = uuid.uuid4(), uuid.uuid4()
    await owner.execute(
        "insert into categories.resort_request (mailbox_id, id, threshold) values ($1, $2, 80)", MAILBOX, request_id
    )
    await owner.execute(
        "insert into categories.plan (mailbox_id, id, list_version, state, cap, kind, request_id, threshold) "
        "values ($1, $2, 1, $3, 50, $4, $5, 80)",
        MAILBOX,
        plan_id,
        state,
        kind,
        request_id,
    )
    for n, sender in enumerate(["Shop <a@shop.example>", "b@shop.example", "Other <c@bank.example>"]):
        await owner.execute(
            "insert into categories.plan_item (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, "
            "old_category_id, new_category_id, old_topic_id, new_topic_id, confidence_pct) "
            "values ($1, $2, $3, 'n', $4, 's', $5, $6, $5, $6, 60)",
            MAILBOX,
            plan_id,
            f"m{n}",
            sender,
            uuid.UUID(OTHER_ID),
            uuid.UUID(category),
        )
    return plan_id, category


async def _mail_item(owner: asyncpg.Connection, message_id: str, verified: str | None) -> None:
    await owner.execute(
        "insert into mail_item (gmail_message_id, thread_id, created_at, urgent, verified_domain) "
        "values ($1, 't', now(), false, $2)",
        message_id,
        verified,
    )


async def test_given_a_ready_review_plan_when_read_then_each_item_has_its_category_domain_subject_and_verified_domain(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan_id, category = await _plan_with_items(cat_owner)
    await _mail_item(cat_owner, "m0", "shop.example")
    await _mail_item(cat_owner, "m1", None)

    rows = await PgTipStore(agent_sessions, MAILBOX).below_threshold(plan_id)

    assert sorted(rows, key=lambda r: (r.sender_domain, r.verified_domain or "")) == [
        TipRow(category, "bank.example", "s", None),
        TipRow(category, "shop.example", "s", None),
        TipRow(category, "shop.example", "s", "shop.example"),
    ]


async def test_given_an_auto_plan_when_read_then_it_has_no_rows(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan_id, _ = await _plan_with_items(cat_owner, kind="auto")

    assert await PgTipStore(agent_sessions, MAILBOX).below_threshold(plan_id) == []


async def test_given_a_tip_when_stored_then_only_the_items_of_that_category_in_a_ready_plan_carry_it(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan_id, category = await _plan_with_items(cat_owner)
    store = PgTipStore(agent_sessions, MAILBOX)

    await store.store_tip(plan_id, category, "Mention bills.")
    await store.store_tip(plan_id, OTHER_ID, "Never for Other.")

    tips = await cat_owner.fetch("select tip from categories.plan_item where plan_id = $1", plan_id)
    assert [r["tip"] for r in tips] == ["Mention bills."] * 3


async def test_given_a_plan_that_is_no_longer_ready_when_a_tip_is_stored_then_nothing_is_written(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan_id, category = await _plan_with_items(cat_owner, state="replaced")

    await PgTipStore(agent_sessions, MAILBOX).store_tip(plan_id, category, "Late tip.")

    assert await cat_owner.fetchval("select count(*) from categories.plan_item where tip is not null") == 0


async def test_given_a_tip_longer_than_the_column_cap_then_postgres_refuses_it(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan_id, category = await _plan_with_items(cat_owner)

    with pytest.raises(Exception, match="ck_plan_item_tip"):
        await PgTipStore(agent_sessions, MAILBOX).store_tip(plan_id, category, "x" * 501)


async def test_given_a_replaced_plan_when_its_items_are_dropped_then_their_tips_go_with_them(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan_id, category = await _plan_with_items(cat_owner)
    await PgTipStore(agent_sessions, MAILBOX).store_tip(plan_id, category, "Mention bills.")

    assert await PgBuildStore(agent_sessions, MAILBOX).replace_plan(plan_id)

    assert await cat_owner.fetchval("select count(*) from categories.plan_item") == 0


async def test_given_an_expired_plan_when_the_purge_runs_then_its_tips_go_with_its_items(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    plan_id, _category = await _plan_with_items(cat_owner, state="discarded")
    await cat_owner.execute(
        "update categories.plan set terminal_at = now() - interval '20 days' where id = $1", plan_id
    )
    await cat_owner.execute("update categories.plan_item set tip = 'Mention bills.' where plan_id = $1", plan_id)

    await cat_owner.execute("select categories.purge_expired()")

    assert await cat_owner.fetchval("select count(*) from categories.plan_item where tip is not null") == 0
