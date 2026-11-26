"""RED-002 on PostgreSQL: the managed set every adapter gets carries the hold while the rename plan is not done (R4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.pg_list_sync import PgLabelBook, PgListSyncStore
from app.db.pg_resort import read_managed_labels
from app.usecases.list_sync import MigrationState
from tests.db.agent_engine import create_agent_engine
from tests.db.conftest import write_list

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

MAILBOX = "mb1"


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    created = create_agent_engine(cat_url)
    yield created
    await created.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return async_sessionmaker(engine, expire_on_commit=False)


class Follower:
    def __init__(self) -> None:
        self.held: list[bool] = []

    def set_managed(self, managed) -> None:  # type: ignore[no-untyped-def]
        self.held.append(managed.writes_held)


@pytest.mark.parametrize(
    ("state", "held"),
    [(None, False), (MigrationState.PENDING, True), (MigrationState.CONFIRMED, True), (MigrationState.DONE, False)],
)
async def test_given_a_migration_state_when_the_managed_labels_are_read_then_the_hold_follows_it(
    sessions: async_sessionmaker,  # type: ignore[type-arg]
    cat_owner: asyncpg.Connection,
    state: MigrationState | None,
    held: bool,
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    if state is not None:  # confirmed is reached through the definer function only; the owner may write it here
        await cat_owner.execute(
            "insert into categories.label_migration (mailbox_id, state) values ($1, 'pending')", MAILBOX
        )
        if state is not MigrationState.PENDING:
            await cat_owner.execute("alter table categories.label_migration disable trigger label_migration_guard")
            await cat_owner.execute(
                "update categories.label_migration set state = $2 where mailbox_id = $1", MAILBOX, state.value
            )

    assert (await read_managed_labels(sessions, MAILBOX)).managed.writes_held is held


async def test_given_a_pending_plan_when_the_book_is_read_then_the_guarded_adapters_get_the_hold(
    sessions: async_sessionmaker,  # type: ignore[type-arg]
    cat_owner: asyncpg.Connection,
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    await PgListSyncStore(sessions, MAILBOX).start_migration(MigrationState.PENDING)
    follower = Follower()

    labels = PgLabelBook(sessions, MAILBOX, dict, followers=(follower,))
    await labels.other()

    assert follower.held == [True]
