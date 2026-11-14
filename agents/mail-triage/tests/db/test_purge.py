"""U-web-settings-49: the owner purge of audit records and expired web rows (AC-21, AC-17, W-13).

The boundary rule, stated once: a security event or an audit record goes when its timestamp is strictly older than the
cutoff (``at < now - retention``); a record exactly as old as the retention stays and goes one run later. Login
requests and sessions follow the rule the web app already uses at start-up (``<=`` on the expiry).
"""
# ruff: noqa: S608  # every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest

from app.db.purge import PurgeCounts, purge_expired
from schedule_policy.testing import FakeClock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

GRANTS = Path(__file__).resolve().parents[2] / "app" / "db" / "grants.sql"
WEB_ROLE = "web_settings_runtime"
AGENT_ROLE = "mail_triage_runtime"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
YEAR = timedelta(days=365)
NINETY = timedelta(days=90)
USER = "u" * 64
SECRET_MARKER = "needle-request-id"  # noqa: S105  # a marker that must never reach a log
_CREATE_ROLES = f"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{WEB_ROLE}') THEN
        CREATE ROLE {WEB_ROLE} LOGIN PASSWORD 'web-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{AGENT_ROLE}') THEN
        CREATE ROLE {AGENT_ROLE} LOGIN PASSWORD 'agent-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$
"""


@pytest.fixture
async def owner(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """The owner connection with the roles made and grants.sql applied, as the migrate job does."""
    connection = await asyncpg.connect(migrated_url.replace("postgresql+asyncpg://", "postgresql://"))
    await connection.execute(_CREATE_ROLES)
    await connection.execute(GRANTS.read_text(encoding="utf-8"))
    yield connection
    await connection.close()


@asynccontextmanager
async def _as(connection: asyncpg.Connection, role: str) -> AsyncIterator[asyncpg.Connection]:
    """Act as a runtime role without logging in as it (the role passwords differ between test files)."""
    await connection.execute(f"set role {role}")
    try:
        yield connection
    finally:
        await connection.execute("reset role")


async def _change(connection: asyncpg.Connection, at: datetime, label: str = "x") -> None:
    await connection.execute(
        "insert into settings.settings_change (at, via, by, db_role, new) values ($1, 'web', $2, 'web_test', '{}')",
        at,
        label,
    )


async def _event(connection: asyncpg.Connection, at: datetime, key: str) -> None:
    await connection.execute(
        "insert into web_auth.security_event "
        '(at, kind, result, username_hash, request_id, client_key, "window", count) '
        "values ($1, 'code_refused', 'refused', $2, $3, $4, 1, 1)",
        at,
        USER,
        SECRET_MARKER,
        key.ljust(64, "k"),
    )


async def _request(connection: asyncpg.Connection, key: str, *, expires_at: datetime, created_at: datetime) -> None:
    await connection.execute(
        "insert into web_auth.login_request (id, username_key, code_hash, client_hash, expires_at, created_at) "
        "values ($1, $2, $3, $4, $5, $6)",
        key,
        USER,
        "h" * 64,
        "c" * 64,
        expires_at,
        created_at,
    )


async def _session(connection: asyncpg.Connection, key: str, *, last_seen: datetime, expires: datetime) -> None:
    await connection.execute(
        "insert into web_auth.session (id_hash, username_hash, last_seen_at, absolute_expires_at) "
        "values ($1, $2, $3, $4)",
        key.ljust(64, "s"),
        USER,
        last_seen,
        expires,
    )


async def _count(connection: asyncpg.Connection, table: str) -> int:
    return int(await connection.fetchval(f"select count(*) from {table}"))


async def _labels(connection: asyncpg.Connection) -> list[str]:
    return [r["by"] for r in await connection.fetch('select "by" from settings.settings_change order by "by"')]


async def _token(connection: asyncpg.Connection, key: str, *, expires_at: datetime) -> None:
    await connection.execute(
        "insert into web_notice_token (token, version, before, created_at, expires_at, burst_id, first_version) "
        "values ($1, 1, '{}', $2, $3, 'b', 1)",
        key,
        expires_at - timedelta(minutes=15),
        expires_at,
    )


# Criterion 1
async def test_given_records_366_and_364_days_old_when_purged_then_only_the_older_one_goes(
    owner: asyncpg.Connection,
) -> None:
    await _change(owner, NOW - timedelta(days=366), "old")
    await _change(owner, NOW - timedelta(days=364), "young")

    counts = await purge_expired(owner, FakeClock(NOW))

    assert counts.settings_change == 1
    assert await _labels(owner) == ["young"]


# Criterion 2
async def test_given_a_record_exactly_365_days_old_when_purged_then_it_stays_and_one_second_older_goes(
    owner: asyncpg.Connection,
) -> None:
    await _change(owner, NOW - YEAR, "exact")
    await _change(owner, NOW - YEAR - timedelta(seconds=1), "older")

    counts = await purge_expired(owner, FakeClock(NOW))

    assert counts.settings_change == 1
    assert await _labels(owner) == ["exact"]
    later = await purge_expired(owner, FakeClock(NOW + timedelta(seconds=1)))
    assert later.settings_change == 1  # the stated rule: it goes once it is strictly older than the retention


async def test_given_a_security_event_exactly_90_days_old_when_purged_then_it_stays_and_a_second_older_goes(
    owner: asyncpg.Connection,
) -> None:
    await _event(owner, NOW - NINETY, "exact")
    await _event(owner, NOW - NINETY - timedelta(seconds=1), "older")

    counts = await purge_expired(owner, FakeClock(NOW))

    assert counts.security_event == 1
    assert await _count(owner, "web_auth.security_event") == 1
    assert (await purge_expired(owner, FakeClock(NOW + timedelta(seconds=1)))).security_event == 1


# Criterion 3
async def test_given_old_events_and_expired_rows_when_purged_then_they_go_and_live_rows_stay(
    owner: asyncpg.Connection,
) -> None:
    await _event(owner, NOW - timedelta(days=91), "old")
    await _event(owner, NOW - timedelta(days=89), "live")
    hour = timedelta(hours=1)
    await _request(owner, "gone", expires_at=NOW - timedelta(minutes=5), created_at=NOW - hour - timedelta(minutes=20))
    await _request(owner, "cap", expires_at=NOW - timedelta(minutes=5), created_at=NOW - timedelta(minutes=20))
    await _request(owner, "live", expires_at=NOW + timedelta(minutes=5), created_at=NOW - timedelta(minutes=5))
    await _session(owner, "absolute", last_seen=NOW, expires=NOW - timedelta(seconds=1))
    await _session(owner, "idle", last_seen=NOW - timedelta(minutes=31), expires=NOW + timedelta(hours=5))
    await _session(owner, "live", last_seen=NOW - timedelta(minutes=5), expires=NOW + timedelta(hours=5))

    counts = await purge_expired(owner, FakeClock(NOW))

    assert counts == PurgeCounts(settings_change=0, security_event=1, login_request=1, session=2, web_notice_token=0)
    assert [r["id"] for r in await owner.fetch("select id from web_auth.login_request order by id")] == ["cap", "live"]
    assert [r["id_hash"][:4] for r in await owner.fetch("select id_hash from web_auth.session")] == ["live"]


async def test_given_the_update_only_guard_on_security_events_when_the_owner_purges_then_the_delete_works(
    owner: asyncpg.Connection,
) -> None:
    await _event(owner, NOW - timedelta(days=200), "old")
    triggers = await owner.fetch(
        "select (tgtype & 8) as is_delete, (tgtype & 16) as is_update, (tgtype & 4) as is_insert from pg_trigger "
        "where tgrelid = 'web_auth.security_event'::regclass and not tgisinternal"
    )
    assert sorted((t["is_delete"], t["is_update"], t["is_insert"]) for t in triggers) == [(0, 0, 4), (0, 16, 0)]

    counts = await purge_expired(owner, FakeClock(NOW))

    assert counts.security_event == 1
    assert await _count(owner, "web_auth.security_event") == 0


# Criterion 4
@pytest.mark.parametrize("role", [AGENT_ROLE, WEB_ROLE])
@pytest.mark.parametrize("statement", ["delete from settings.settings_change", "truncate settings.settings_change"])
async def test_given_a_runtime_role_when_it_deletes_or_truncates_the_audit_then_it_is_refused_with_42501(
    owner: asyncpg.Connection, role: str, statement: str
) -> None:
    await _change(owner, NOW - timedelta(days=400))
    async with _as(owner, role):
        with pytest.raises(asyncpg.InsufficientPrivilegeError) as refused:
            await owner.execute(statement)
    assert refused.value.sqlstate == "42501"
    assert await _count(owner, "settings.settings_change") == 1
    await purge_expired(owner, FakeClock(NOW))  # the owner purge stays the one delete path
    assert await _count(owner, "settings.settings_change") == 0


# Criterion 7
async def test_given_a_purge_when_the_logs_are_captured_then_only_the_counts_appear(
    owner: asyncpg.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    await _event(owner, NOW - timedelta(days=200), "old")
    await _change(owner, NOW - timedelta(days=800), "who-was-here")

    with caplog.at_level(logging.DEBUG):
        await purge_expired(owner, FakeClock(NOW))

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "security_event=1" in text
    assert "settings_change=1" in text
    for forbidden in (SECRET_MARKER, USER, "who-was-here", "web_test"):
        assert forbidden not in text


# Criterion 8
async def test_given_a_purge_when_it_runs_twice_then_the_second_removes_nothing(owner: asyncpg.Connection) -> None:
    await _change(owner, NOW - timedelta(days=500))
    await _event(owner, NOW - timedelta(days=100), "old")
    await _session(owner, "old", last_seen=NOW - timedelta(days=1), expires=NOW - timedelta(hours=1))

    first = await purge_expired(owner, FakeClock(NOW))
    second = await purge_expired(owner, FakeClock(NOW))

    assert first == PurgeCounts(settings_change=1, security_event=1, login_request=0, session=1, web_notice_token=0)
    assert second == PurgeCounts(settings_change=0, security_event=0, login_request=0, session=0, web_notice_token=0)


# Criterion 2 (U-web-settings-71, SEC3-04)
async def test_given_an_expired_and_a_live_notice_token_when_purged_then_only_the_expired_one_goes(
    owner: asyncpg.Connection,
) -> None:
    await _token(owner, "expired", expires_at=NOW - timedelta(minutes=1))
    await _token(owner, "live", expires_at=NOW + timedelta(minutes=1))

    counts = await purge_expired(owner, FakeClock(NOW))

    assert counts.web_notice_token == 1
    assert [r["token"] for r in await owner.fetch("select token from web_notice_token")] == ["live"]


async def test_given_a_notice_token_expiring_exactly_now_when_purged_then_it_goes_and_one_second_earlier_it_stays(
    owner: asyncpg.Connection,
) -> None:
    await _token(owner, "edge", expires_at=NOW)

    assert (await purge_expired(owner, FakeClock(NOW - timedelta(seconds=1)))).web_notice_token == 0
    assert await _count(owner, "web_notice_token") == 1
    assert (await purge_expired(owner, FakeClock(NOW))).web_notice_token == 1
    assert await _count(owner, "web_notice_token") == 0


async def test_given_an_expired_notice_token_when_purged_then_the_log_has_the_count_and_never_the_token(
    owner: asyncpg.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    await _token(owner, "secret-token-value", expires_at=NOW - timedelta(hours=1))

    with caplog.at_level(logging.INFO, logger="app.db.purge"):
        await purge_expired(owner, FakeClock(NOW))

    assert "web_notice_token=1" in caplog.text
    assert "secret-token-value" not in caplog.text
