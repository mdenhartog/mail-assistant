"""U-mail-categories-05, criteria 4 and 6 in PostgreSQL (AC-39, AC-37): the list read and the ``filing`` write."""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.alert_state import AlertState
from app.core.alert_text import AuthResults
from app.core.judgement import OTHER_ID
from app.db.pg_conversation import ConversationStore
from app.db.pg_store import PgStore
from app.usecases.overview import SecurityMail
from app.usecases.triage import FilingEntry, MailContent, Outcome
from tests.db.conftest import write_list

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncEngine

MAILBOX = "mb1"


@pytest.fixture
async def engine(cat_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(cat_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgStore:
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return PgStore(sessions, ConversationStore(sessions, lambda: datetime.now(UTC)), mailbox_id=MAILBOX)


def outcome(label: str | None, filing: FilingEntry | None) -> Outcome:
    content = MailContent(
        sender="boss@example.com",
        subject="Budget",
        reply_to=None,
        has_attachment=False,
        reason="r",
        summary="s",
        auth=AuthResults(None, None, None),
    )
    return Outcome(label=label, urgent=False, confidence=0.9, alert=None, note="", content=content, filing=filing)


async def test_given_two_list_versions_when_the_current_list_is_read_then_it_is_the_latest_in_order(
    store: PgStore, cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await write_list(cat_api, MAILBOX, 1, ["Bills"])
    await write_list(cat_api, MAILBOX, 2, ["Bills", "Travel"])
    await write_list(cat_api, "mb2", 1, ["Work"])
    ids = {
        r["name"]: str(r["id"])
        for r in await cat_owner.fetch(
            "select id, name from categories.category where mailbox_id = $1 and version = 2", MAILBOX
        )
    }

    current = await store.current_list()

    assert current.version == 2
    assert [(c.category_id, c.name) for c in current.categories] == [(ids["Bills"], "Bills"), (ids["Travel"], "Travel")]


async def test_given_no_list_yet_when_the_current_list_is_read_then_it_is_version_zero_and_empty(
    store: PgStore, cat_owner: asyncpg.Connection
) -> None:
    del cat_owner

    current = await store.current_list()

    assert (current.version, current.categories) == (0, ())


async def test_given_a_filed_mail_when_completed_then_the_filing_row_has_ids_and_version_only(
    store: PgStore, cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await write_list(cat_api, MAILBOX, 1, ["Bills"])
    bills = await cat_owner.fetchval("select id from categories.category where mailbox_id = $1", MAILBOX)
    await store.claim("m1", "t1")
    await store.claim("m2", "t2")

    await store.complete("m1", outcome("Assistant/Bills", FilingEntry(str(bills), 1)))
    await store.complete("m2", outcome("Assistant/Other", FilingEntry(OTHER_ID, 1)))

    rows = await cat_owner.fetch("select * from categories.filing order by message_id")
    assert [(r["mailbox_id"], r["message_id"], r["list_version"], r["category_id"]) for r in rows] == [
        (MAILBOX, "m1", 1, bills),
        (MAILBOX, "m2", 1, uuid.UUID(OTHER_ID)),
    ]
    assert set(rows[0].keys()) == {
        "mailbox_id",
        "message_id",
        "list_version",
        "category_id",
        "filed_at",
        "topic_id",
        "extra_id",
        "source",
        "source_ref",
    }  # no mail text; source_ref is the matched sender entry, nothing of the mail itself


async def test_given_a_pinned_mail_when_completed_then_no_filing_row_is_written_and_the_overview_skips_it(
    store: PgStore, cat_owner: asyncpg.Connection
) -> None:
    await store.claim("m1", "t1")

    await store.complete("m1", outcome(None, None))

    assert await cat_owner.fetchval("select count(*) from categories.filing") == 0
    assert await store.filed_without_alert_since(datetime(2000, 1, 1, tzinfo=UTC)) == []


async def test_given_pinned_google_security_mail_when_completed_then_an_alert_exists_and_the_overview_lists_it(
    store: PgStore, cat_owner: asyncpg.Connection
) -> None:
    await store.claim("sec", "t1")
    await store.claim("code", "t2")
    base = outcome(None, None)
    security = replace(base, urgent=True, alert=AlertState.OPEN, note="pinned:google_security", confidence=None)
    sign_in = replace(
        base,
        note="pinned:sign_in_code",
        confidence=None,
        content=replace(base.content, sender="", subject=""),
    )

    await store.complete("sec", security)
    await store.complete("code", sign_in)

    assert await cat_owner.fetchval("select count(*) from alert") == 1
    since = datetime(2000, 1, 1, tzinfo=UTC)
    assert await store.filed_without_alert_since(since) == []
    assert await store.security_mail_since(since) == [SecurityMail("boss@example.com", "Budget")]


async def test_given_the_same_mail_completed_twice_when_retried_then_there_is_still_one_filing_row(
    store: PgStore, cat_owner: asyncpg.Connection, cat_api: asyncpg.Connection
) -> None:
    await write_list(cat_api, MAILBOX, 1, ["Bills"])
    await store.claim("m1", "t1")
    entry = FilingEntry(OTHER_ID, 1)

    await store.complete("m1", outcome("Assistant/Other", entry))
    await store.complete("m1", outcome("Assistant/Other", entry))

    assert await cat_owner.fetchval("select count(*) from categories.filing") == 1
