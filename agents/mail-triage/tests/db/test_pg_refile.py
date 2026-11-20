"""U-mail-categories-25, criteria 1, 3 and 5 (AC-46, AC-30): the re-file report on the real database as the agent role.

Every test acts as the agent role (``resort_support``), so the grants are part of what is tested. Gmail is a fake.
"""
# every statement is a fixed test literal inside a throwaway container, never user input

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from app.adapters.gmail_read import FetchedMail
from app.db.pg_refile import PgRefileStore
from app.usecases.refile_report import Filed, RefileReport, RefileReportService
from tests.db.resort_support import MAILBOX, OTHER_ID, agent_sessions, seed_list

if TYPE_CHECKING:
    import asyncpg
    from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ["agent_sessions"]  # the fixture is used by name

NOW = datetime(2026, 12, 1, 6, 0, tzinfo=UTC)
CANARY_SENDER = "canary-sender@example.invalid"
CANARY_SUBJECT = "canary-subject-4711"


async def _file(owner: asyncpg.Connection, message_id: str, category: str, version: int, age_days: float) -> None:
    """A filing row as the agent writes it, then backdated by the owner (the time is the database's)."""
    await owner.execute(
        "insert into categories.filing (mailbox_id, message_id, list_version, category_id, filed_at) "
        "values ($1, $2, $3, $4::uuid, now() - $5 * interval '1 day')",
        MAILBOX,
        message_id,
        version,
        category,
        age_days,
    )


async def _label(owner: asyncpg.Connection, category: str, label_id: str, name: str, mailbox: str = MAILBOX) -> None:
    await owner.execute(
        "insert into categories.category_identity (mailbox_id, id) values ($1, $2::uuid) on conflict do nothing",
        mailbox,
        category,
    )
    await owner.execute(
        "insert into categories.category_label (mailbox_id, category_id, label_id, label_name) "
        "values ($1, $2::uuid, $3, $4)",
        mailbox,
        category,
        label_id,
        name,
    )


@dataclass
class Gmail:
    names: dict[str, str]
    mails: dict[str, set[str]] = field(default_factory=dict)
    fetched: list[str] = field(default_factory=list)

    def label_names(self) -> dict[str, str]:
        return dict(self.names)

    def fetch(self, message_id: str) -> FetchedMail | None:
        self.fetched.append(message_id)
        labels = self.mails.get(message_id)
        if labels is None:
            return None
        return FetchedMail(
            message_id=message_id,
            thread_id="t",
            sender=CANARY_SENDER,
            reply_to=None,
            subject=CANARY_SUBJECT,
            text="body",
            has_attachment=False,
            headers={},
            labels=frozenset(labels),
        )


async def test_given_filings_when_asked_then_the_newest_row_of_each_mail_in_the_period_comes_newest_first(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    finance, travel = await seed_list(cat_owner, ["Finance", "Travel"])
    await _file(cat_owner, "a", finance, 1, 10)
    await _file(cat_owner, "a", travel, 2, 3)  # a was filed again under a newer list version
    await _file(cat_owner, "b", finance, 1, 1)
    await _file(cat_owner, "old", finance, 1, 20)  # outside the period
    await cat_owner.execute("insert into categories.mailbox (id) values ('other') on conflict do nothing")
    await cat_owner.execute(
        "insert into categories.filing (mailbox_id, message_id, list_version, category_id) "
        "values ('other', 'x', 1, $1::uuid)",
        finance,
    )  # another mailbox
    store = PgRefileStore(agent_sessions, MAILBOX)

    found = await store.filings_since(datetime.now(UTC) - timedelta(days=14))

    assert found == [Filed("b", finance), Filed("a", travel)]


async def test_given_labels_when_asked_then_the_map_holds_every_category_and_other_for_this_mailbox_only(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    finance = (await seed_list(cat_owner, ["Finance"]))[0]
    await _label(cat_owner, finance, "L_FIN", "Assistant/Finance")
    await _label(cat_owner, OTHER_ID, "L_OTH", "Assistant/Other")
    await seed_list(cat_owner, ["Elsewhere"], mailbox="mb2")
    await _label(cat_owner, str(uuid.uuid4()), "L_X", "Assistant/Elsewhere", mailbox="mb2")
    store = PgRefileStore(agent_sessions, MAILBOX)

    assert await store.category_labels() == {finance: "L_FIN", OTHER_ID: "L_OTH"}


async def test_given_filings_in_14_days_when_the_report_runs_as_the_agent_then_it_reports_and_records_the_shares(
    cat_owner: asyncpg.Connection,
    agent_sessions: async_sessionmaker[Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    finance, travel = await seed_list(cat_owner, ["Finance", "Travel"])
    await _label(cat_owner, finance, "L_FIN", "Assistant/Finance")
    await _label(cat_owner, travel, "L_TRV", "Assistant/Travel")
    await _label(cat_owner, OTHER_ID, "L_OTH", "Assistant/Other")
    gmail = Gmail(
        {"L_FIN": "Assistant/Finance", "L_TRV": "Assistant/Travel", "L_OTH": "Assistant/Other", "INBOX": "INBOX"}
    )
    plan = [("kept", finance, "L_FIN")] * 6 + [("moved", finance, "L_TRV")] * 2 + [("other", OTHER_ID, "L_OTH")] * 2
    for index, (kind, category, now_label) in enumerate(plan):
        message_id = f"{kind}{index}"
        await _file(cat_owner, message_id, category, 1, index / 10)
        gmail.mails[message_id] = {"INBOX", now_label}
    await _file(cat_owner, "gone1", finance, 1, 2)
    store = PgRefileStore(agent_sessions, MAILBOX)
    service = RefileReportService(store, gmail, now=lambda: datetime.now(UTC), max_checked=100)

    with caplog.at_level(logging.INFO):
        report = await service.run_once()

    assert report == RefileReport(filed=11, checked=11, refiled=2, in_other=2, gone=1)
    assert report.refiled_percent == pytest.approx(100 * 2 / 11)
    assert report.other_percent == pytest.approx(100 * 2 / 11)
    row = await cat_owner.fetchrow("select * from categories.refile_report")
    assert row is not None
    assert (row["mailbox_id"], row["filed"], row["checked"], row["refiled"], row["in_other"], row["gone"]) == (
        MAILBOX,
        11,
        11,
        2,
        2,
        1,
    )
    assert "refiled=2" in caplog.text


async def test_given_more_filings_than_the_cap_when_the_report_runs_then_gmail_is_asked_for_the_cap_at_most(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any]
) -> None:
    finance = (await seed_list(cat_owner, ["Finance"]))[0]
    await _label(cat_owner, finance, "L_FIN", "Assistant/Finance")
    gmail = Gmail({"L_FIN": "Assistant/Finance"})
    for index in range(30):
        await _file(cat_owner, f"m{index:02d}", finance, 1, index / 10)  # m00 is the newest
        gmail.mails[f"m{index:02d}"] = {"L_FIN"}
    service = RefileReportService(
        PgRefileStore(agent_sessions, MAILBOX), gmail, now=lambda: datetime.now(UTC), max_checked=7
    )

    report = await service.run_once()

    assert gmail.fetched == [f"m{index:02d}" for index in range(7)]
    assert (report.filed, report.checked) == (30, 7)
    row = await cat_owner.fetchrow("select filed, checked from categories.refile_report")
    assert row is not None
    assert (row["filed"], row["checked"]) == (30, 7)


async def test_given_canary_strings_when_the_report_runs_then_no_sender_or_subject_is_in_the_row_or_the_log(
    cat_owner: asyncpg.Connection, agent_sessions: async_sessionmaker[Any], caplog: pytest.LogCaptureFixture
) -> None:
    finance = (await seed_list(cat_owner, ["Finance"]))[0]
    await _label(cat_owner, finance, "L_FIN", "Assistant/Finance")
    gmail = Gmail({"L_FIN": "Assistant/Finance", "L_TRV": "Assistant/Travel"})
    for index, now_label in enumerate(["L_FIN", "L_TRV", "L_TRV"]):
        await _file(cat_owner, f"canary-msg-{index}", finance, 1, 1)
        gmail.mails[f"canary-msg-{index}"] = {now_label}
    service = RefileReportService(
        PgRefileStore(agent_sessions, MAILBOX), gmail, now=lambda: datetime.now(UTC), max_checked=100
    )

    with caplog.at_level(logging.DEBUG):
        report = await service.run_once()

    rows = await cat_owner.fetch("select * from categories.refile_report")
    seen = repr(report) + repr([dict(row) for row in rows]) + caplog.text
    assert CANARY_SENDER not in seen
    assert CANARY_SUBJECT not in seen
    assert "canary-msg" not in seen  # no message id either
