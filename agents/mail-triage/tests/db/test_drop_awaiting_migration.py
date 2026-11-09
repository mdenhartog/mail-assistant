"""U-quiet-hours-06b: migration 0005 moves an open question to the conversation row and drops alert.awaiting_input.

Covers ADR-0026 against a real PostgreSQL.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
from alembic import command

from app.db.pg_conversation import NO_EXPIRY
from tests.db.conftest import alembic_config

APP = Path(__file__).resolve().parents[2] / "app"


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _migrate(url: str, revision: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), revision)


async def _downgrade(url: str, revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(url), revision)


async def _fetch(url: str, sql: str) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(_plain(url))
    try:
        return await connection.fetch(sql)
    finally:
        await connection.close()


async def _execute(url: str, sql: str) -> None:
    connection = await asyncpg.connect(_plain(url))
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


def _mail_and_alert(n: int, awaiting: str | None, updated: str) -> str:
    value = "null" if awaiting is None else f"'{awaiting}'"
    return (
        f"insert into mail_item (id, gmail_message_id, thread_id, urgent, created_at) "  # noqa: S608 - test seed, ints only
        f"values ({n}, 'm{n}', 't{n}', true, now()); "
        f"insert into alert (id, mail_item_id, state, due_at, awaiting_input, created_at, updated_at) "
        f"values ({n}, {n}, 'held', now(), {value}, now(), '{updated}')"
    )


async def _alert_columns(url: str) -> set[str]:
    rows = await _fetch(url, "select column_name from information_schema.columns where table_name='alert'")
    return {r["column_name"] for r in rows}


async def test_given_revision_0004_with_a_pending_snooze_question_when_migrated_then_the_conversation_row_holds_it(
    database_url: str,
) -> None:
    await _migrate(database_url, "0004")
    await _execute(database_url, _mail_and_alert(7, "snooze_hours", "2026-11-09 10:00+00"))

    await _migrate(database_url, "head")

    [row] = await _fetch(database_url, "select id, kind, target, step, partial, nonce, expires_at from conversation")
    assert (row["id"], row["kind"], row["target"], row["step"]) == (1, "snooze", "7", "hours")
    assert row["expires_at"] == NO_EXPIRY
    assert len(row["nonce"]) >= 16
    assert "awaiting_input" not in await _alert_columns(database_url)
    alerts = await _fetch(database_url, "select id, state from alert")
    assert [(a["id"], a["state"]) for a in alerts] == [(7, "held")]


async def test_given_revision_0004_with_a_pending_reply_question_when_migrated_then_it_becomes_a_reply_text_step(
    database_url: str,
) -> None:
    await _migrate(database_url, "0004")
    await _execute(database_url, _mail_and_alert(3, "reply_text", "2026-11-09 10:00+00"))

    await _migrate(database_url, "head")

    [row] = await _fetch(database_url, "select kind, target, step from conversation")
    assert (row["kind"], row["target"], row["step"]) == ("reply", "3", "text")


async def test_given_several_alerts_with_a_question_when_migrated_then_the_most_recently_updated_one_is_kept(
    database_url: str,
) -> None:
    await _migrate(database_url, "0004")
    await _execute(database_url, _mail_and_alert(1, "snooze_hours", "2026-11-09 09:00+00"))
    await _execute(database_url, _mail_and_alert(2, "reply_text", "2026-11-09 11:00+00"))
    await _execute(database_url, _mail_and_alert(3, "snooze_hours", "2026-11-09 10:00+00"))

    await _migrate(database_url, "head")

    rows = await _fetch(database_url, "select kind, target, step from conversation")
    assert [(r["kind"], r["target"], r["step"]) for r in rows] == [("reply", "2", "text")]


async def test_given_no_pending_question_or_an_unknown_value_when_migrated_then_no_conversation_row_appears(
    database_url: str,
) -> None:
    await _migrate(database_url, "0004")
    await _execute(database_url, _mail_and_alert(1, None, "2026-11-09 09:00+00"))
    await _execute(database_url, _mail_and_alert(2, "something_else", "2026-11-09 10:00+00"))

    await _migrate(database_url, "head")

    assert await _fetch(database_url, "select 1 from conversation") == []
    assert len(await _fetch(database_url, "select 1 from alert")) == 2


async def test_given_a_conversation_already_pending_when_migrated_then_it_is_not_overwritten(
    database_url: str,
) -> None:
    await _migrate(database_url, "0004")
    await _execute(database_url, _mail_and_alert(1, "snooze_hours", "2026-11-09 09:00+00"))
    await _execute(
        database_url,
        "insert into conversation (id, kind, step, nonce, expires_at) "
        "values (1, 'settings', 'start', 'keep-me', now())",
    )

    await _migrate(database_url, "head")

    rows = await _fetch(database_url, "select kind, nonce from conversation")
    assert [(r["kind"], r["nonce"]) for r in rows] == [("settings", "keep-me")]


async def test_given_0005_with_a_pending_question_when_downgraded_and_upgraded_again_then_nothing_is_lost(
    database_url: str,
) -> None:
    await _migrate(database_url, "0004")
    await _execute(database_url, _mail_and_alert(5, "reply_text", "2026-11-09 10:00+00"))
    await _migrate(database_url, "head")

    await _downgrade(database_url, "0004")

    assert "awaiting_input" in await _alert_columns(database_url)
    back = await _fetch(database_url, "select id, state, awaiting_input from alert")
    assert [(r["id"], r["state"], r["awaiting_input"]) for r in back] == [(5, "held", "reply_text")]

    await _migrate(database_url, "head")

    [row] = await _fetch(database_url, "select kind, target, step from conversation")
    assert (row["kind"], row["target"], row["step"]) == ("reply", "5", "text")
    assert "awaiting_input" not in await _alert_columns(database_url)
    assert len(await _fetch(database_url, "select 1 from alert")) == 1


async def test_given_a_settings_conversation_when_downgraded_then_no_question_is_put_back_on_an_alert(
    database_url: str,
) -> None:
    await _migrate(database_url, "head")
    await _execute(database_url, _mail_and_alert_no_column())
    await _execute(
        database_url,
        "insert into conversation (id, kind, step, nonce, expires_at) values (1, 'settings', 'start', 'n', now())",
    )

    await _downgrade(database_url, "0004")

    rows = await _fetch(database_url, "select awaiting_input from alert")
    assert [r["awaiting_input"] for r in rows] == [None]


def _mail_and_alert_no_column() -> str:
    return (
        "insert into mail_item (id, gmail_message_id, thread_id, urgent, created_at) "
        "values (1, 'm1', 't1', true, now()); "
        "insert into alert (id, mail_item_id, state, due_at, created_at, updated_at) "
        "values (1, 1, 'held', now(), now(), now())"
    )


def test_given_the_app_sources_when_searched_for_awaiting_input_then_there_is_no_hit() -> None:
    hits = [
        str(path.relative_to(APP))
        for path in APP.rglob("*")
        if path.is_file() and path.suffix in {".py", ".sql"} and "awaiting_input" in path.read_text(encoding="utf-8")
    ]

    assert hits == []
