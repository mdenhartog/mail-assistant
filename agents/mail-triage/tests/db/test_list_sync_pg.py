"""U-label-prefix-removal-05 on PostgreSQL: the store the sync writes through and the label book, as the agent role."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapters.gmail_resort import GmailResort
from app.core.managed import ManagedLabel, ManagedSet, Role
from app.db.models import OTHER_ID
from app.db.pg_list_sync import PgLabelBook, PgListSyncStore
from app.usecases.list_sync import LabelKey, LabelSettings, ListSync, MigrationState, StoredLabel
from tests.db.agent_engine import create_agent_engine
from tests.db.conftest import AGENT_ROLE, write_list
from tests.fakes.fake_gmail import FakeGmail

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    import asyncpg

MAILBOX = "mb1"


@pytest.fixture
async def engine(cat_owner: asyncpg.Connection, cat_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine whose connections act as the agent role: the grants are part of what is tested."""
    created = create_agent_engine(cat_url)
    yield created
    await created.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def store(sessions: async_sessionmaker) -> PgListSyncStore:  # type: ignore[type-arg]
    return PgListSyncStore(sessions, MAILBOX)


async def category_ids(store: PgListSyncStore) -> dict[str, uuid.UUID]:
    return {c.name: c.id for c in (await store.current_list()).categories}


async def test_given_no_state_when_started_twice_then_the_first_state_stands(
    store: PgListSyncStore, cat_api: asyncpg.Connection
) -> None:
    assert await store.migration_state() is None

    assert await store.start_migration(MigrationState.PENDING) is MigrationState.PENDING
    assert await store.start_migration(MigrationState.DONE) is MigrationState.PENDING

    assert await store.migration_state() is MigrationState.PENDING
    assert await cat_api.fetchval("select state from categories.label_migration where mailbox_id = $1", MAILBOX) == (
        "pending"
    )


async def test_given_a_mailbox_without_a_row_when_the_state_starts_then_the_mailbox_row_is_made(
    sessions: async_sessionmaker,  # type: ignore[type-arg]
    cat_owner: asyncpg.Connection,
) -> None:
    fresh = PgListSyncStore(sessions, "mb-new")

    await fresh.start_migration(MigrationState.DONE)

    assert await cat_owner.fetchval("select count(*) from categories.mailbox where id = 'mb-new'") == 1


async def test_given_no_settings_row_when_the_names_are_read_then_the_defaults_come_back(
    store: PgListSyncStore, cat_owner: asyncpg.Connection
) -> None:
    assert await store.label_settings() == LabelSettings("Other", "Archive")
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    assert await store.label_settings() == LabelSettings("Other", "Archive")  # a version without a settings row


async def test_given_settings_in_two_versions_when_the_names_are_read_then_the_latest_wins(
    store: PgListSyncStore, cat_owner: asyncpg.Connection
) -> None:
    for version, other in ((1, "Overig"), (2, "Rest")):
        async with cat_owner.transaction():
            await cat_owner.execute(
                "insert into categories.list_version (mailbox_id, version) values ($1, $2)", MAILBOX, version
            )
            await cat_owner.execute(
                "insert into categories.list_settings (mailbox_id, version, other_label, archive_label) "
                "values ($1, $2, $3, $4)",
                MAILBOX,
                version,
                other,
                "Bewaard",
            )

    assert await store.label_settings() == LabelSettings("Rest", "Bewaard")


async def test_given_a_managed_label_when_saved_twice_then_the_latest_id_and_name_are_kept(
    store: PgListSyncStore, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    category = (await category_ids(store))["Bills"]
    key = LabelKey("category", category)

    await store.save_managed(key, "Label_1", "Bills")
    await store.save_managed(key, "Label_2", "Invoices")
    await store.save_managed(LabelKey("other"), "Label_3", "Other")
    await store.save_managed(LabelKey("other"), "Label_4", "Overig")
    await store.save_managed(LabelKey("archive"), "Label_5", "Archive")

    assert await store.managed_ids() == {
        key: StoredLabel("Label_2", "Invoices"),
        LabelKey("other"): StoredLabel("Label_4", "Overig"),
        LabelKey("archive"): StoredLabel("Label_5", "Archive"),
    }


async def test_given_old_derived_rows_when_replaced_then_only_the_new_ones_remain(
    store: PgListSyncStore, cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    category = (await category_ids(store))["Bills"]
    await store.replace_derived({category: 3, OTHER_ID: 1}, ["Bills", "Old"])

    await store.replace_derived({category: 4}, ["Bills"])

    rows = await cat_api.fetch("select category_id, mail_count from categories.category_count")
    assert {r["category_id"]: r["mail_count"] for r in rows} == {category: 4}
    assert [r["name"] for r in await cat_api.fetch("select name from categories.gmail_label")] == ["Bills"]


async def test_given_a_cursor_when_advanced_then_it_reads_back_and_starts_at_zero(store: PgListSyncStore) -> None:
    assert await store.cursor() == 0

    await store.advance_cursor(1)
    await store.advance_cursor(2)

    assert await store.cursor() == 2


async def test_given_no_list_when_the_sync_runs_on_postgres_then_nothing_is_seeded_and_the_labels_are_made(
    store: PgListSyncStore, cat_api: asyncpg.Connection
) -> None:
    gmail = FakeGmail()
    gmail.add_label("Work")

    result = await ListSync(GmailResort(gmail, ManagedSet(()), sleep=lambda _s: None), store).run()

    assert (result.version, await store.cursor()) == (0, 0)
    assert await cat_api.fetchval("select count(*) from categories.list_version") == 0
    assert {"Other", "Archive"} <= set(gmail.label_names())
    assert {key.kind for key in await store.managed_ids()} == {"other", "archive"}


async def test_given_a_list_when_the_sync_runs_twice_on_postgres_then_the_ids_counts_and_cursor_exist_once(
    store: PgListSyncStore, cat_api: asyncpg.Connection, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    gmail = FakeGmail()
    sync = ListSync(GmailResort(gmail, ManagedSet(()), sleep=lambda _s: None), store)

    await sync.run()
    gmail.calls.clear()
    await sync.run()

    assert [c for c in gmail.calls if c in ("labels.create", "labels.patch", "messages.modify")] == []
    assert await store.cursor() == 1
    assert await cat_api.fetchval("select count(*) from categories.category_count") == 2  # Bills and Other
    assert {r["name"] for r in await cat_api.fetch("select name from categories.gmail_label")} == {
        "Bills",
        "Other",
        "Archive",
    }
    assert await cat_api.fetchval("select state from categories.label_migration") == "done"


async def test_given_a_pending_mailbox_when_the_sync_runs_on_postgres_then_nothing_is_written_to_gmail_or_the_table(
    store: PgListSyncStore, cat_owner: asyncpg.Connection
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    gmail = FakeGmail()
    gmail.add_label("Assistant/Bills")

    await ListSync(GmailResort(gmail, ManagedSet(()), sleep=lambda _s: None), store).run()

    assert await store.migration_state() is MigrationState.PENDING
    assert [c for c in gmail.calls if c in ("labels.create", "labels.patch", "messages.modify")] == []
    assert await store.managed_ids() == {}
    assert await store.cursor() == 0


async def test_given_the_test_engine_when_it_connects_then_it_acts_as_the_agent_role(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        assert (await connection.exec_driver_sql("select session_user")).scalar_one() == AGENT_ROLE


# --- the label book --------------------------------------------------------------------------------------------------


class Follower:
    def __init__(self) -> None:
        self.seen: list[ManagedSet] = []

    def set_managed(self, managed: ManagedSet) -> None:
        self.seen.append(managed)


def book(sessions: async_sessionmaker, names: dict[str, str] | None = None, *, follower: Follower | None = None):  # type: ignore[no-untyped-def,type-arg]
    return PgLabelBook(sessions, MAILBOX, lambda: dict(names or {}), followers=(follower,) if follower else ())


async def test_given_stored_ids_when_the_book_is_read_then_it_has_the_list_labels_other_and_the_archive(
    sessions: async_sessionmaker,  # type: ignore[type-arg]
    store: PgListSyncStore,
    cat_owner: asyncpg.Connection,
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    bills = (await category_ids(store))["Bills"]
    await store.save_managed(LabelKey("category", bills), "L_B", "Bills")
    await store.save_managed(LabelKey("other"), "L_O", "Other")
    follower = Follower()
    labels = book(sessions, follower=follower)

    managed = await labels.managed()

    assert (await labels.topic(str(bills))) == ManagedLabel("Bills", "L_B", Role.TOPIC)
    assert (await labels.other()) == ManagedLabel("Other", "L_O", Role.OTHER)
    assert managed.archive == ManagedLabel("Archive", None, Role.ARCHIVE)
    assert follower.seen  # the adapters that guard writes get the same set


async def test_given_a_label_id_when_remembered_then_it_is_stored_for_its_category_other_and_archive(
    sessions: async_sessionmaker,  # type: ignore[type-arg]
    store: PgListSyncStore,
    cat_owner: asyncpg.Connection,
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    bills = (await category_ids(store))["Bills"]
    labels = book(sessions)

    await labels.remember(await labels.topic(str(bills)), "L_1")
    await labels.remember(await labels.other(), "L_2")
    await labels.remember(ManagedLabel("Archive", None, Role.ARCHIVE), "L_3")
    await labels.remember(await labels.topic(str(bills)), "L_4")  # the label was made again

    assert await store.managed_ids() == {
        LabelKey("category", bills): StoredLabel("L_4", "Bills"),
        LabelKey("other"): StoredLabel("L_2", "Other"),
        LabelKey("archive"): StoredLabel("L_3", "Archive"),
    }


async def test_given_the_names_when_asked_twice_then_gmail_is_asked_once_until_an_id_is_remembered(
    sessions: async_sessionmaker,  # type: ignore[type-arg]
    cat_owner: asyncpg.Connection,
) -> None:
    await write_list(cat_owner, MAILBOX, 1, ["Bills"])
    asked: list[int] = []

    def names() -> dict[str, str]:
        asked.append(1)
        return {"L_1": "Bills"}

    labels = PgLabelBook(sessions, MAILBOX, names)

    assert await labels.names() == {"L_1": "Bills"}
    assert await labels.names() == {"L_1": "Bills"}
    assert len(asked) == 1
    await labels.remember(await labels.other(), "L_2")  # a label was made: the names are out of date
    await labels.names()
    assert len(asked) == 2
