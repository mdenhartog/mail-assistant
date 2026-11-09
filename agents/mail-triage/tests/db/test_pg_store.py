"""The PostgreSQL store behind the use cases (ADR-0020; spec AC-12, AC-20, AC-22, AC-31)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.alert_state import AlertState
from app.core.alert_text import AuthResults
from app.db.pg_store import PgStore
from app.usecases.reply import StoredDraft
from app.usecases.triage import Claim, MailContent, Outcome

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgStore:
    return PgStore(async_sessionmaker(engine, expire_on_commit=False))


def content(**changes: object) -> MailContent:
    base = {
        "sender": "boss@example.com",
        "subject": "Budget",
        "reply_to": None,
        "has_attachment": False,
        "reason": "Due Friday",
        "summary": "Pay it",
        "auth": AuthResults("pass", "pass", "fail"),
    }
    return MailContent(**{**base, **changes})  # type: ignore[arg-type]


def outcome(
    label: str = "Assistant/Finance",
    *,
    alert: AlertState | None = None,
    confidence: float | None = 0.9,
    **changes: object,
) -> Outcome:
    return Outcome(
        label=label,
        urgent=alert is not None,
        confidence=confidence,
        alert=alert,
        note="",
        content=content(**changes),
    )


async def add(store: PgStore, message_id: str, result: Outcome) -> None:
    assert await store.claim(message_id, f"t-{message_id}") is Claim.NEW
    await store.complete(message_id, result)


async def test_given_the_same_mail_twice_when_claimed_then_the_state_follows_its_progress(store: PgStore) -> None:
    assert await store.claim("m1", "t1") is Claim.NEW
    assert await store.claim("m1", "t1") is Claim.PENDING  # claimed, never completed: a crash

    await store.complete("m1", outcome())

    assert await store.claim("m1", "t1") is Claim.DONE


async def test_given_a_mail_that_was_given_up_on_when_claimed_then_it_is_done(store: PgStore) -> None:
    await store.claim("m1", "t1")
    for expected in (1, 2, 3):
        assert await store.record_failure("m1") == expected

    await store.abandon("m1")

    assert await store.claim("m1", "t1") is Claim.DONE


async def test_given_no_position_when_read_then_none_and_a_saved_position_is_returned(store: PgStore) -> None:
    assert await store.history_id() is None

    await store.save_history_id("100")
    await store.save_history_id("200")

    assert await store.history_id() == "200"


async def test_given_filed_mails_when_labels_are_asked_then_each_label_is_listed_once(store: PgStore) -> None:
    await add(store, "m1", outcome("Assistant/Finance"))
    await add(store, "m2", outcome("Assistant/Finance"))
    await add(store, "m3", outcome("Assistant/Travel"))
    await store.claim("m4", "t4")  # claimed, no label yet

    assert sorted(await store.known_labels()) == ["Assistant/Finance", "Assistant/Travel"]


async def test_given_an_urgent_mail_when_completed_then_an_alert_with_its_content_can_be_delivered(
    store: PgStore,
) -> None:
    await add(store, "m1", outcome(alert=AlertState.OPEN, reply_to="x@example.net", has_attachment=True))

    [pending] = await store.unsent()

    assert pending.state is AlertState.OPEN
    assert pending.meta.sender == "boss@example.com"
    assert pending.meta.subject == "Budget"
    assert pending.meta.reply_to == "x@example.net"
    assert pending.meta.has_attachment is True
    assert pending.judgement.reason == "Due Friday"
    assert pending.judgement.summary == "Pay it"
    assert pending.auth == AuthResults("pass", "pass", "fail")


async def test_given_a_mail_without_alert_when_completed_then_nothing_is_waiting_for_delivery(store: PgStore) -> None:
    await add(store, "m1", outcome())

    assert await store.unsent() == []
    assert await store.held() == []


async def test_given_a_sent_alert_when_asked_again_then_it_is_not_unsent_and_counts_for_the_hour(
    store: PgStore,
) -> None:
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()

    await store.mark_sent(pending.alert_id, 4242, at=NOW)

    assert await store.unsent() == []
    assert await store.sent_since(NOW - timedelta(hours=1)) == 1
    assert await store.sent_since(NOW + timedelta(minutes=1)) == 0


async def test_given_a_held_alert_when_released_then_it_is_open_and_unsent(store: PgStore) -> None:
    await add(store, "m1", outcome(alert=AlertState.HELD))
    [held] = await store.held()
    assert await store.unsent() == []

    await store.release(held.alert_id)

    assert await store.held() == []
    assert [a.alert_id for a in await store.unsent()] == [held.alert_id]


RELEASE_AT = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)


async def test_given_a_held_alert_with_a_release_moment_when_completed_then_the_moment_is_stored_and_listed(
    store: PgStore,
) -> None:
    await add(store, "m1", replace(outcome(alert=AlertState.HELD), release_at=RELEASE_AT))

    [held] = await store.held()

    assert held.release_at == RELEASE_AT


async def test_given_a_backlog_mail_with_a_held_alert_when_completed_then_its_release_moment_is_stored(
    store: PgStore,
) -> None:
    assert await store.claim("m1", "t-m1") is Claim.NEW

    await store.complete_backlog("m1", replace(outcome(alert=AlertState.HELD), release_at=RELEASE_AT))

    [held] = await store.held()
    assert held.release_at == RELEASE_AT


async def test_given_an_open_alert_when_completed_then_it_has_no_release_moment(store: PgStore) -> None:
    await add(store, "m1", outcome(alert=AlertState.HELD))

    [held] = await store.held()

    assert held.release_at is None


async def test_given_a_snoozed_alert_when_held_again_then_the_release_moment_is_stored_and_cleared_on_release(
    store: PgStore,
) -> None:
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    await store.set_state(pending.alert_id, AlertState.SNOOZED, due_at=NOW)

    await store.set_state(pending.alert_id, AlertState.HELD, resend=True, release_at=RELEASE_AT)
    [held] = await store.held()
    await store.release(held.alert_id)

    assert held.release_at == RELEASE_AT
    assert held.alert_id == pending.alert_id
    [released] = await store.unsent()
    assert released.release_at is None


async def test_given_a_snoozed_alert_when_due_then_it_is_listed_and_resending_makes_it_unsent_again(
    store: PgStore,
) -> None:
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    await store.mark_sent(pending.alert_id, 1, at=NOW)

    await store.set_state(pending.alert_id, AlertState.SNOOZED, due_at=NOW + timedelta(hours=3))
    assert await store.state_of(pending.alert_id) is AlertState.SNOOZED
    assert await store.due_snoozed(NOW + timedelta(hours=2)) == []
    assert await store.due_snoozed(NOW + timedelta(hours=3, minutes=1)) == [pending.alert_id]

    await store.set_state(pending.alert_id, AlertState.OPEN, resend=True)

    assert [a.alert_id for a in await store.unsent()] == [pending.alert_id]


async def test_given_an_unknown_alert_when_asked_then_none(store: PgStore) -> None:
    assert await store.state_of("999") is None
    assert await store.state_of("not-a-number") is None
    assert await store.alert_info("999") is None


async def test_given_an_alert_when_asked_for_its_info_then_state_and_gmail_id_are_returned(store: PgStore) -> None:
    await add(store, "gm-1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()

    info = await store.alert_info(pending.alert_id)

    assert info is not None
    assert (info.state, info.gmail_message_id) == (AlertState.OPEN, "gm-1")


def draft(alert_id: str, draft_id: str = "d1", digest: str = "a" * 64) -> StoredDraft:
    return StoredDraft(draft_id, alert_id, None, "Yes", digest, NOW + timedelta(minutes=15), used=False)


async def test_given_a_draft_when_consumed_then_it_works_once_and_only_with_the_right_digest(store: PgStore) -> None:
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    await store.save_draft(draft(pending.alert_id))

    assert await store.get_draft("d1") == draft(pending.alert_id)
    assert await store.consume_draft("d1", "b" * 64, now=NOW) is None
    assert await store.consume_draft("d1", "a" * 64, now=NOW + timedelta(minutes=16)) is None
    consumed = await store.consume_draft("d1", "a" * 64, now=NOW)
    assert consumed is not None
    assert consumed.body == "Yes"
    assert await store.consume_draft("d1", "a" * 64, now=NOW) is None


async def test_given_drafts_of_an_alert_when_invalidated_then_none_can_be_used_any_more(store: PgStore) -> None:
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    await store.save_draft(draft(pending.alert_id, "d1"))
    await store.save_draft(draft(pending.alert_id, "d2"))

    await store.invalidate_drafts(pending.alert_id)

    assert await store.consume_draft("d1", "a" * 64, now=NOW) is None
    assert await store.consume_draft("d2", "a" * 64, now=NOW) is None
    assert await store.get_draft("missing") is None


async def test_given_audit_entries_when_written_then_they_hold_kind_alert_and_digest_but_no_content(
    store: PgStore, engine: AsyncEngine
) -> None:
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()

    await store.record_audit("alert_sent", pending.alert_id)
    await store.record_audit("reply_drafted", pending.alert_id, "f" * 64)

    async with engine.connect() as connection:
        rows = (await connection.execute(text("select kind, ref, digest from audit_log order by id"))).all()
    assert [tuple(r) for r in rows] == [
        ("alert_sent", pending.alert_id, None),
        ("reply_drafted", pending.alert_id, "f" * 64),
    ]


async def test_given_the_overview_when_asked_then_only_unalerted_mails_since_the_start_are_listed(
    store: PgStore, engine: AsyncEngine
) -> None:
    await add(store, "old", outcome("Assistant/Finance"))
    async with engine.begin() as connection:
        await connection.execute(
            text("update mail_item set created_at = :t where gmail_message_id = 'old'"), {"t": NOW - timedelta(days=2)}
        )
    await add(store, "quiet", outcome("Assistant/Newsletters", confidence=0.4, sender="n@example.com", subject="Hi"))
    await add(store, "loud", outcome(alert=AlertState.OPEN))

    listed = await store.filed_without_alert_since(NOW - timedelta(days=1))

    assert [(m.label, m.confidence, m.sender, m.subject) for m in listed] == [
        ("Assistant/Newsletters", 0.4, "n@example.com", "Hi")
    ]


async def test_given_the_overview_day_when_marked_then_it_is_remembered(store: PgStore) -> None:
    day = date(2026, 11, 9)
    assert await store.overview_sent(day) is False

    await store.mark_overview_sent(day)
    await store.mark_overview_sent(day)  # twice is fine

    assert await store.overview_sent(day) is True
    assert await store.overview_sent(date(2026, 11, 10)) is False


async def test_given_marco_is_asked_for_input_when_he_answers_then_the_waiting_alert_is_found_and_cleared(
    store: PgStore,
) -> None:
    await add(store, "m1", outcome(alert=AlertState.OPEN))
    [pending] = await store.unsent()
    assert await store.awaiting() is None

    await store.set_awaiting(pending.alert_id, "snooze_hours")

    assert await store.awaiting() == (pending.alert_id, "snooze_hours")
    await store.set_awaiting(pending.alert_id, None)
    assert await store.awaiting() is None


async def test_given_old_mail_content_when_purged_then_the_content_is_gone_and_the_decision_stays(
    store: PgStore, engine: AsyncEngine
) -> None:
    await add(store, "old", outcome(alert=AlertState.OPEN, reply_to="x@example.net"))
    await add(store, "new", outcome(alert=AlertState.OPEN))
    async with engine.begin() as connection:
        await connection.execute(
            text("update mail_item set created_at = :t where gmail_message_id = 'old'"), {"t": NOW - timedelta(days=31)}
        )

    purged = await store.purge_content(NOW - timedelta(days=30))

    assert purged == 1
    async with engine.connect() as connection:
        old = (
            await connection.execute(
                text(
                    "select sender, subject, reply_to, reason, summary, label, urgent "
                    "from mail_item where gmail_message_id = 'old'"
                )
            )
        ).one()
        new = (await connection.execute(text("select sender from mail_item where gmail_message_id = 'new'"))).one()
    assert tuple(old) == (None, None, None, None, None, "Assistant/Finance", True)
    assert new[0] == "boss@example.com"


# ---- U-backlog-02: the catch-up state and its alerts (INT-003, AC-B4, AC-B5, AC-B10) --------------------------------


async def _count(engine: AsyncEngine, sql: str) -> int:
    async with engine.connect() as connection:
        return int((await connection.execute(text(sql))).scalar_one())


async def test_given_no_catch_up_when_its_state_is_read_then_it_is_none(store: PgStore) -> None:
    assert await store.catchup_state() is None


async def test_given_a_started_catch_up_when_started_again_later_then_the_first_start_time_stays(
    store: PgStore,
) -> None:
    await store.start_catchup(NOW)
    await store.start_catchup(NOW + timedelta(hours=3))

    state = await store.catchup_state()
    assert state is not None
    assert state.started_at == NOW
    assert state.finished_at is None


async def test_given_two_starts_at_the_same_moment_when_they_race_then_one_row_exists(
    store: PgStore, engine: AsyncEngine
) -> None:
    await asyncio.gather(store.start_catchup(NOW), store.start_catchup(NOW + timedelta(seconds=1)))

    assert await _count(engine, "select count(*) from catchup_state") == 1


async def test_given_a_finished_catch_up_when_a_new_store_reads_it_then_it_is_still_finished(
    store: PgStore, engine: AsyncEngine
) -> None:
    await store.start_catchup(NOW)
    await store.finish_catchup(NOW + timedelta(hours=1))

    state = await PgStore(async_sessionmaker(engine, expire_on_commit=False)).catchup_state()

    assert state is not None
    assert state.finished_at == NOW + timedelta(hours=1)


async def test_given_a_finished_catch_up_when_finished_again_then_the_first_finish_time_stays(store: PgStore) -> None:
    await store.start_catchup(NOW)
    await store.finish_catchup(NOW + timedelta(hours=1))
    await store.finish_catchup(NOW + timedelta(hours=9))

    state = await store.catchup_state()
    assert state is not None
    assert state.finished_at == NOW + timedelta(hours=1)


async def test_given_an_old_mail_with_an_alert_when_completed_as_backlog_then_it_is_flagged_and_has_one_alert(
    store: PgStore, engine: AsyncEngine
) -> None:
    assert await store.claim("old1", "t-old1") is Claim.NEW

    await store.complete_backlog("old1", outcome(alert=AlertState.OPEN))

    assert await _count(engine, "select count(*) from mail_item where backlog and completed") == 1
    assert await _count(engine, "select count(*) from alert") == 1


async def test_given_a_normal_mail_when_completed_then_it_is_not_flagged_as_backlog(
    store: PgStore, engine: AsyncEngine
) -> None:
    await add(store, "new1", outcome(alert=AlertState.OPEN))

    assert await _count(engine, "select count(*) from mail_item where backlog") == 0


async def test_given_complete_backlog_runs_twice_when_the_second_call_comes_then_there_is_still_one_alert(
    store: PgStore, engine: AsyncEngine
) -> None:
    assert await store.claim("old1", "t-old1") is Claim.NEW
    await store.complete_backlog("old1", outcome(alert=AlertState.OPEN))

    await store.complete_backlog("old1", outcome(alert=AlertState.OPEN))

    assert await _count(engine, "select count(*) from alert") == 1


async def test_given_backlog_alerts_in_any_state_and_a_normal_alert_when_counted_then_only_backlog_alerts_count(
    store: PgStore, engine: AsyncEngine
) -> None:
    for message_id, state in (("o1", AlertState.OPEN), ("o2", AlertState.HELD), ("o3", AlertState.OPEN)):
        assert await store.claim(message_id, f"t-{message_id}") is Claim.NEW
        await store.complete_backlog(message_id, outcome(alert=state))
    async with engine.begin() as connection:
        await connection.execute(text("update alert set state = 'closed' where id = (select min(id) from alert)"))
        await connection.execute(text("update alert set state = 'snoozed' where id = (select max(id) from alert)"))
    await add(store, "n1", outcome(alert=AlertState.OPEN))
    assert await store.claim("o4", "t-o4") is Claim.NEW
    await store.complete_backlog("o4", outcome(alert=None))  # urgent or not, no alert row: not counted

    assert await store.backlog_alerts() == 3


async def test_given_urgent_and_normal_mail_without_alerts_when_listed_then_urgent_is_set_only_for_urgent(
    store: PgStore,
) -> None:
    urgent_without_alert = replace(outcome("Assistant/Finance"), urgent=True, alert=None)
    for message_id, result in (("u1", urgent_without_alert), ("n1", outcome("Assistant/Newsletter"))):
        assert await store.claim(message_id, f"t-{message_id}") is Claim.NEW
        await store.complete_backlog(message_id, result)

    filed = await store.filed_without_alert_since(NOW - timedelta(days=1))

    assert {(mail.label, mail.urgent) for mail in filed} == {
        ("Assistant/Finance", True),
        ("Assistant/Newsletter", False),
    }


async def test_given_an_urgent_mail_filed_yesterday_when_the_next_overview_is_listed_then_it_is_not_listed_again(
    store: PgStore, engine: AsyncEngine
) -> None:
    assert await store.claim("u1", "t-u1") is Claim.NEW
    await store.complete_backlog("u1", replace(outcome("Assistant/Finance"), urgent=True, alert=None))
    async with engine.begin() as connection:
        await connection.execute(text("update mail_item set created_at = now() - interval '1 day'"))
    start_of_today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    assert await store.filed_without_alert_since(start_of_today) == []
