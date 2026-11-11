"""U-web-settings-13: the security event store against a real PostgreSQL, written as the web role.

Lives in tests/db because the shared database fixture is there.
"""

import logging
from datetime import timedelta

import asyncpg
import pytest
from sqlalchemy import text

from app.auth.digest import username_digest
from app.db import Database
from app.security_events import SecurityEvents
from tests.fakes import FakeClock

KEY = b"k" * 32
CLIENT = "203.0.113.7"
SELECT = 'select kind, result, username_hash, request_id, client_key, "window" from web_auth.security_event order by id'


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def events(web_database: Database, clock: FakeClock) -> SecurityEvents:
    return SecurityEvents(web_database, clock)


def _lines(records: list[logging.LogRecord]) -> list[str]:
    return [r.getMessage() for r in records if r.name == "app.security_events"]


# Criterion 1
async def test_given_a_code_refused_for_the_canary_user_when_recorded_then_only_the_digest_is_stored(
    events: SecurityEvents, owner: asyncpg.Connection, canary_log_records: list[logging.LogRecord]
) -> None:
    digest = username_digest(KEY, "canary-user")

    await events.record("code_refused", "req-1", CLIENT, digest)

    rows = await owner.fetch(SELECT)
    assert len(rows) == 1
    row = rows[0]
    assert (row["kind"], row["result"], row["request_id"], row["client_key"]) == (
        "code_refused",
        "refused",
        "req-1",
        CLIENT,
    )
    assert row["username_hash"].strip() == digest
    assert "canary-user" not in repr([tuple(r) for r in rows])
    assert not [r for r in canary_log_records if "canary-user" in r.getMessage()]


# Criterion 2
async def test_given_ten_identical_events_when_recorded_then_one_row_and_a_second_after_the_window(
    events: SecurityEvents, owner: asyncpg.Connection, clock: FakeClock
) -> None:
    for _ in range(10):
        await events.record("rate_limited", "req-1", CLIENT)
    clock.advance(timedelta(seconds=59, milliseconds=900))
    await events.record("rate_limited", "req-2", CLIENT)
    assert await owner.fetchval("select count(*) from web_auth.security_event") == 1

    clock.advance(timedelta(milliseconds=100))
    await events.record("rate_limited", "req-3", CLIENT)

    rows = await owner.fetch(SELECT)
    assert [r["request_id"] for r in rows] == ["req-1", "req-3"]
    assert rows[1]["window"] == rows[0]["window"] + 1


async def test_given_the_same_event_from_two_clients_when_recorded_then_both_are_kept(
    events: SecurityEvents, owner: asyncpg.Connection
) -> None:
    await events.record("rate_limited", "req-1", CLIENT)
    await events.record("rate_limited", "req-2", "203.0.113.8")

    assert await owner.fetchval("select count(*) from web_auth.security_event") == 2


# Criterion 3
async def test_given_two_kinds_from_one_client_when_recorded_then_both_are_kept(
    events: SecurityEvents, owner: asyncpg.Connection
) -> None:
    await events.record("csrf_refused", "req-1", CLIENT)
    await events.record("lock_refused", "req-1", CLIENT)

    rows = await owner.fetch(SELECT)
    assert [(r["kind"], r["result"]) for r in rows] == [("csrf_refused", "refused"), ("lock_refused", "refused")]


# Criterion 4
async def test_given_a_recorded_event_when_logged_then_one_line_has_kind_result_request_id(
    events: SecurityEvents, canary_log_records: list[logging.LogRecord]
) -> None:
    await events.record("code_refused", "req-9", "2001:db8::1", username_digest(KEY, "canary-user"))

    lines = _lines(canary_log_records)
    assert len(lines) == 1
    line = lines[0]
    assert "kind=code_refused" in line
    assert "result=refused" in line
    assert "client=ipv6" in line
    assert "request_id=req-9" in line
    assert "2001:db8" not in line
    assert username_digest(KEY, "canary-user") not in line


# Criterion 5 is in test_unknown_kind_is_refused_before_the_database below.


# Criterion 6
async def test_given_the_insert_fails_when_recorded_then_nothing_is_raised_and_only_the_error_class_is_logged(
    events: SecurityEvents, owner: asyncpg.Connection, canary_log_records: list[logging.LogRecord]
) -> None:
    await owner.execute("alter table web_auth.security_event rename to security_event_gone")

    await events.record("code_refused", "req-1", CLIENT)

    lines = _lines(canary_log_records)
    assert len(lines) == 1
    assert "security_event.failed" in lines[0]
    assert "error_class=" in lines[0]
    assert "security_event_gone" not in lines[0]
    assert "insert" not in lines[0].lower()
    assert all(r.exc_info is None for r in canary_log_records if r.name == "app.security_events")


async def test_given_a_username_hash_that_is_not_a_digest_when_recorded_then_it_is_refused(
    events: SecurityEvents, owner: asyncpg.Connection
) -> None:
    with pytest.raises(ValueError, match="username hash"):
        await events.record("code_refused", "req-1", CLIENT, "canary-user")

    assert await owner.fetchval("select count(*) from web_auth.security_event") == 0


# Criterion 7
async def test_given_a_mail_failed_event_when_recorded_then_it_carries_no_address_and_no_error_text(
    events: SecurityEvents, owner: asyncpg.Connection, canary_log_records: list[logging.LogRecord]
) -> None:
    await events.record("mail_failed", "req-1", CLIENT)

    row = (await owner.fetch(SELECT))[0]
    assert (row["kind"], row["result"], row["username_hash"]) == ("mail_failed", "failed", None)
    assert "@" not in repr(tuple(row))
    assert "@" not in " ".join(_lines(canary_log_records))


async def test_the_web_role_can_only_insert_events(web_database: Database) -> None:
    async with web_database.session() as session:
        with pytest.raises(Exception, match="permission denied"):
            await session.execute(text("delete from web_auth.security_event"))


# Criterion 5
async def test_unknown_kind_is_refused_before_the_database(clock: FakeClock) -> None:
    class NoDatabase:
        def session(self) -> None:
            msg = "the database must not be touched"
            raise AssertionError(msg)

    store = SecurityEvents(NoDatabase(), clock)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="event kind"):
        await store.record("login; drop table x", "req-1", CLIENT)
