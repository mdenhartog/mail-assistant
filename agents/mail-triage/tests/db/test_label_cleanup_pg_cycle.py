"""U-label-prefix-removal-09, criteria 1, 4, 5 and 7 on PostgreSQL: the real lease, the record, a restart.

The Gmail side is the in-memory mailbox with the real delete adapter; the store is the PostgreSQL one with the agent
role.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapters.gmail_label_delete import GmailLabelDelete
from app.adapters.gmail_resort import GmailResort
from app.core.managed import ManagedSet
from app.db.pg_label_cleanup import PgLabelCleanupStore
from app.usecases.label_cleanup import LabelCleanup
from tests.db.agent_engine import create_agent_engine
from tests.fakes.fake_gmail import FakeGmail
from tests.usecases.test_label_cleanup import CANARY, CYCLE, NOW, WAIT, Chat, SlowDelete, until

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

MAILBOX = "mb1"


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    """The agent's engine; the rename plan of the mailbox is ``done`` (no items: ``pending`` may go to ``done``)."""
    created = create_agent_engine(cat_url, pool_size=6)
    await cat_owner.execute(
        "insert into categories.label_migration (mailbox_id, state) values ($1, 'pending')", MAILBOX
    )
    await cat_owner.execute("update categories.label_migration set state = 'done' where mailbox_id = $1", MAILBOX)
    yield created
    await created.dispose()


def store_for(engine: AsyncEngine) -> PgLabelCleanupStore:
    return PgLabelCleanupStore(async_sessionmaker(engine, expire_on_commit=False), MAILBOX)


def step(gmail: FakeGmail, delete: GmailLabelDelete, store: PgLabelCleanupStore, chat: Chat) -> LabelCleanup:
    return LabelCleanup(
        GmailResort(gmail, ManagedSet(()), sleep=lambda _s: None), delete, store, chat, now=lambda: NOW, cycle=CYCLE
    )


async def ripen(store: PgLabelCleanupStore, label_id: str) -> None:
    """A timer that started a wait and a cycle ago and was seen empty at the previous cycle."""
    await store.start_timer(label_id, NOW - WAIT - CYCLE, WAIT)
    await store.touch(label_id, NOW - CYCLE)


async def test_given_two_overlapping_cycles_on_one_database_when_both_run_then_the_label_is_deleted_once(
    engine: AsyncEngine, cat_owner: asyncpg.Connection
) -> None:
    gmail = FakeGmail()
    slow = SlowDelete(gmail)
    label = gmail.add_label(CANARY)
    await ripen(store_for(engine), label)
    first = asyncio.create_task(step(gmail, slow, store_for(engine), Chat()).run_once())
    await until(slow.entered.is_set)  # the first cycle is inside the delete call and holds the advisory lock

    second = await step(gmail, slow, store_for(engine), Chat()).run_once()
    slow.release.set()
    done = await first

    assert (done.deleted, second.deleted, second.leased_out) == (1, 0, True)
    assert gmail.calls.count("labels.delete") == 1
    assert await cat_owner.fetchval("select count(*) from categories.deleted_label") == 1
    assert await cat_owner.fetchval("select count(*) from categories.label_empty_since") == 0


async def test_given_a_delete_when_recorded_then_the_name_is_kept_and_the_hash_of_the_id_is_stored(
    engine: AsyncEngine, cat_owner: asyncpg.Connection
) -> None:
    gmail = FakeGmail()
    label = gmail.add_label(CANARY)
    store = store_for(engine)
    await ripen(store, label)

    await step(gmail, GmailLabelDelete(gmail, sleep=lambda _s: None), store, Chat()).run_once()

    row = await cat_owner.fetchrow("select mailbox_id, label_id_hash, name, deleted_at from categories.deleted_label")
    assert row is not None
    assert (row["mailbox_id"], row["label_id_hash"], row["name"], row["deleted_at"]) == (
        MAILBOX,
        hashlib.sha256(label.encode()).hexdigest(),
        CANARY,
        NOW,
    )


async def test_given_the_canary_label_when_a_cycle_runs_then_it_is_in_deleted_label_only_and_nowhere_else(
    engine: AsyncEngine, cat_owner: asyncpg.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    gmail = FakeGmail()
    label = gmail.add_label(CANARY)
    store = store_for(engine)
    chat = Chat()
    await ripen(store, label)
    caplog.set_level(logging.DEBUG)

    await step(gmail, GmailLabelDelete(gmail, sleep=lambda _s: None), store, chat).run_once()

    assert CANARY not in caplog.text
    assert all(CANARY not in text for text in chat.texts)
    tables = await cat_owner.fetch(
        "select table_schema, table_name from information_schema.tables "
        "where table_schema in ('categories', 'settings') and table_type = 'BASE TABLE'"
    )
    holding = []
    for table in tables:
        name = table["table_name"]
        rows = await cat_owner.fetch(f"select t::text as row from {table['table_schema']}.{name} t")  # noqa: S608
        if any(CANARY in row["row"] for row in rows):
            holding.append(name)
    assert holding == ["deleted_label"]


async def test_given_a_running_timer_and_a_lowered_wait_when_the_agent_restarts_then_the_timer_keeps_its_wait(
    engine: AsyncEngine, cat_owner: asyncpg.Connection
) -> None:
    gmail = FakeGmail()
    label = gmail.add_label("A1")
    await store_for(engine).start_timer(label, NOW - timedelta(hours=2), timedelta(hours=12))
    await store_for(engine).touch(label, NOW - CYCLE)
    await cat_owner.execute(
        "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, "
        "updated_by, label_wait_minutes) values (1, 'Europe/Amsterdam', 600, 900, 1080, 540, 'web', 'u1', 5)"
    )

    restarted = step(gmail, GmailLabelDelete(gmail, sleep=lambda _s: None), store_for(engine), Chat())  # a new process
    result = await restarted.run_once()

    assert result.deleted == 0
    assert label in gmail.label_table
    assert await cat_owner.fetchval("select wait_minutes from categories.label_empty_since") == 720


async def test_given_a_migration_that_is_not_done_when_a_cycle_runs_on_the_database_then_nothing_is_deleted(
    engine: AsyncEngine, cat_owner: asyncpg.Connection
) -> None:
    await cat_owner.execute("delete from categories.label_migration")
    await cat_owner.execute("insert into categories.label_migration (mailbox_id, state) values ('mb1', 'pending')")
    gmail = FakeGmail()
    label = gmail.add_label("A1")
    store = store_for(engine)
    await ripen(store, label)

    result = await step(gmail, GmailLabelDelete(gmail, sleep=lambda _s: None), store, Chat()).run_once()

    assert result.blocked is True
    assert "labels.delete" not in gmail.calls
