"""U-label-structure-14, criteria 1, 3 and 4 on the real database: the audit rows and a list confirmed mid-filing."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.sender_rules import FilingSource
from app.db.pg_conversation import ConversationStore
from app.db.pg_store import PgStore
from app.usecases.triage import FilingEntry, MailContent, Outcome
from tests.db.conftest import API_ROLE, connect_as

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncEngine

MAILBOX = "mb1"
FROM_CANARY = "canary-from-6e1d@unmatched-canary.nl"
SUBJECT_CANARY = "canary-subject-0b52"
BODY_CANARY = "canary-body-93aa"
TIMEOUT = 20.0  # a barrier that is never reached fails the test instead of hanging it


@dataclass(frozen=True)
class Version:
    """What one list version must read as, whole."""

    number: int
    name: str
    senders: tuple[str, ...]
    instructions: str


V1 = Version(1, "Huis", (), "")
V2 = Version(2, "Woning", ("julianahoeve.nl",), "Be brief")


@pytest.fixture
async def engine(cat_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(cat_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgStore:
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return PgStore(sessions, ConversationStore(sessions, lambda: datetime.now(UTC)), mailbox_id=MAILBOX)


def _outcome(filing: FilingEntry) -> Outcome:
    content = MailContent(
        sender=FROM_CANARY,
        subject=SUBJECT_CANARY,
        reply_to=None,
        has_attachment=False,
        reason="r",
        summary=BODY_CANARY,
        verified_domain=None,
    )
    return Outcome(
        label="Assistant/Huis", urgent=False, confidence=0.9, alert=None, note="", content=content, filing=filing
    )


async def _write(
    connection: asyncpg.Connection,
    version: Version,
    identity: uuid.UUID,
    inserted: asyncio.Event | None = None,
    commit: asyncio.Event | None = None,
) -> None:
    """An upload confirm in one transaction: ``inserted`` is set once written, the commit waits for ``commit``."""
    async with connection.transaction():
        await connection.execute(
            "insert into categories.list_version (mailbox_id, version) values ($1, $2)", MAILBOX, version.number
        )
        if version.number == 1:
            await connection.execute(
                "insert into categories.category_identity (mailbox_id, id) values ($1, $2)", MAILBOX, identity
            )
        await connection.execute(
            "insert into categories.category (mailbox_id, version, id, name, description, position) "
            "values ($1, $2, $3, $4, 'd', 0)",
            MAILBOX,
            version.number,
            identity,
            version.name,
        )
        for entry in version.senders:
            await connection.execute(
                "insert into categories.category_sender (mailbox_id, version, category_id, entry, is_domain) "
                "values ($1, $2, $3, $4, true)",
                MAILBOX,
                version.number,
                identity,
                entry,
            )
        await connection.execute(
            "insert into categories.list_settings (mailbox_id, version, general_instructions, archive_label) "
            "values ($1, $2, $3, 'Assistant/Archive')",
            MAILBOX,
            version.number,
            version.instructions,
        )
        if inserted is not None and commit is not None:
            inserted.set()
            await asyncio.wait_for(commit.wait(), TIMEOUT)


async def _snapshot(store: PgStore) -> Version:
    current = await store.current_list()
    (category,) = current.categories
    senders = tuple(s.text for s in category.senders)
    return Version(current.version, category.name, senders, current.general_instructions)


async def test_given_an_upload_confirm_in_flight_when_mail_is_filed_then_it_sees_the_old_list_whole_then_the_new_whole(
    store: PgStore, cat_owner: asyncpg.Connection, cat_url: str
) -> None:
    identity = uuid.uuid4()
    await _write(cat_owner, V1, identity)
    writer = await connect_as(cat_url, API_ROLE)
    inserted, commit = asyncio.Event(), asyncio.Event()
    try:
        confirm = asyncio.create_task(_write(writer, V2, identity, inserted, commit))
        await asyncio.wait_for(inserted.wait(), TIMEOUT)  # barrier 1: the new version is written, not committed
        during = await _snapshot(store)
        await store.claim("m1", "t1")
        await store.complete("m1", _outcome(FilingEntry(str(identity), during.number)))
        commit.set()  # barrier 2: the confirm commits
        await asyncio.wait_for(confirm, TIMEOUT)
        after = await _snapshot(store)
        await store.claim("m2", "t2")
        await store.complete("m2", _outcome(FilingEntry(str(identity), after.number)))
    finally:
        await writer.close()

    assert during == V1  # the old version, every part of it
    assert after == V2  # the new version, every part of it
    rows = await cat_owner.fetch("select message_id, list_version from categories.filing order by message_id")
    assert [(r["message_id"], r["list_version"]) for r in rows] == [
        ("m1", 1),
        ("m2", 2),
    ]  # the record names the version


async def test_given_mail_read_while_a_version_commits_when_many_snapshots_are_taken_then_none_is_a_mix(
    store: PgStore, cat_owner: asyncpg.Connection, cat_url: str
) -> None:
    identity = uuid.uuid4()
    await _write(cat_owner, V1, identity)
    writer = await connect_as(cat_url, API_ROLE)
    inserted, commit = asyncio.Event(), asyncio.Event()
    seen: list[Version] = []

    async def reader() -> None:
        await asyncio.wait_for(inserted.wait(), TIMEOUT)
        while len(seen) < 60:
            seen.append(await _snapshot(store))
            if len(seen) == 20:
                commit.set()  # the commit lands in the middle of the reads

    try:
        confirm = asyncio.create_task(_write(writer, V2, identity, inserted, commit))
        await asyncio.wait_for(asyncio.gather(reader(), confirm), TIMEOUT)
    finally:
        await writer.close()

    assert set(seen) <= {V1, V2}  # never a new name with the old senders, or the other way round
    assert (seen[0], seen[-1]) == (V1, V2)


async def test_given_filings_and_list_changes_when_the_audit_rows_are_read_then_they_name_source_and_hold_no_mail_text(
    store: PgStore, cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    identity = uuid.uuid4()
    await _write(cat_api, V1, identity)
    await _write(cat_api, V2, identity)
    entries = {
        "m1": FilingEntry(str(identity), 2, None, FilingSource.SENDER_RULE, "julianahoeve.nl"),
        "m2": FilingEntry(str(identity), 2, None, FilingSource.SENDER_RULE_NOT_APPLIED, "julianahoeve.nl"),
        "m3": FilingEntry(str(identity), 2),
    }
    for message_id, filing in entries.items():
        await store.claim(message_id, f"t-{message_id}")
        await store.complete(message_id, _outcome(filing))

    audit = await cat_owner.fetch("select channel, actor_digest from categories.list_audit order by version")
    assert [r["channel"] for r in audit] == ["web", "web"]
    assert all(re.fullmatch(r"[0-9a-f]{64}", r["actor_digest"]) for r in audit)  # a digest, never a name
    filings = await cat_owner.fetch("select source, source_ref from categories.filing order by message_id")
    assert [(r["source"], r["source_ref"]) for r in filings] == [
        ("sender_rule", "julianahoeve.nl"),
        ("sender_rule_not_applied", "julianahoeve.nl"),
        ("model", None),
    ]
    tables = await cat_owner.fetch("select tablename from pg_tables where schemaname = 'categories'")
    for table in (r["tablename"] for r in tables):  # every row of every table of the schema, as text
        rows = await cat_owner.fetch(f"select t::text as row from categories.{table} t")  # noqa: S608
        dump = "\n".join(r["row"] for r in rows)
        assert [c for c in (FROM_CANARY, SUBJECT_CANARY, BODY_CANARY) if c in dump] == [], table
