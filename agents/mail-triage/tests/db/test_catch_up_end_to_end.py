"""U-backlog-11a: the catch-up end to end on a real PostgreSQL (INT-003; AC-B1 to AC-B15).

Replays 2026-11-08: dozens of unread mails were in the inbox before the agent started. Gmail, Telegram and Anthropic are
fakes with a little memory (Gmail knows labels, Anthropic judges by a word in the text); the database is real. All
time comes from one controllable clock, so there is no sleeping and no flakiness.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.adapters.gmail_read import FetchedMail
from app.settings import load_settings
from app.usecases.catchup import BACKLOG_ALERT_LIMIT, BUDGET_RESERVE
from app.wiring import build_runner
from tests.test_settings import VALID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from app.runner import Runner

DAY_ONE = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # 13:00 in Amsterdam
DAY_TWO_NIGHT = datetime(2026, 11, 10, 22, 30, tzinfo=UTC)  # 23:30 in Amsterdam: quiet hours, a new UTC day
DAY_THREE_MORNING = datetime(2026, 11, 11, 6, 30, tzinfo=UTC)  # 07:30 in Amsterdam: quiet hours are over
SENTINEL = "BODY-SENTINEL-77c1"
UNREAD_INBOX = {"INBOX", "UNREAD"}


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at

    def today(self) -> str:
        return self.at.date().isoformat()


class StatefulGmail:
    """An inbox that remembers labels. Newest mail is listed first, like Gmail does."""

    def __init__(self) -> None:
        self.labels: dict[str, set[str]] = {}
        self.order: list[str] = []  # newest first
        self.pending_new: list[str] = []
        self.texts: dict[str, str] = {}
        self.filed: list[str] = []
        self.sent: list[str] = []

    def add(self, mail_id: str, labels: set[str], body: str = "an ordinary mail") -> None:
        self.labels[mail_id] = set(labels)
        self.texts[mail_id] = f"{body} {SENTINEL}"
        self.order.append(mail_id)

    def arrive(self, mail_id: str, body: str = "a new mail") -> None:
        self.labels[mail_id] = set(UNREAD_INBOX)
        self.texts[mail_id] = f"{body} {SENTINEL}"
        self.order.insert(0, mail_id)
        self.pending_new.append(mail_id)

    def list_new(self, history_id: str | None) -> tuple[list[str], str]:
        new, self.pending_new = self.pending_new, []
        return ([], "100") if history_id is None else (new, "200")

    def list_unread_before(self, cutoff: datetime) -> list[str]:
        assert cutoff.tzinfo is not None
        return [i for i in self.order if self.labels[i] >= UNREAD_INBOX]

    def fetch(self, message_id: str) -> FetchedMail:
        return FetchedMail(
            message_id=message_id,
            thread_id=f"t-{message_id}",
            sender=f"{message_id}@example.com",
            reply_to=None,
            subject=f"Subject of {message_id}",
            text=self.texts[message_id],
            has_attachment=False,
            headers={},
            labels=frozenset(self.labels[message_id]),
        )

    def ensure_label(self, name: str) -> str:
        return f"id:{name}"

    def file(self, message_id: str, label_id: str) -> None:
        self.labels[message_id].discard("INBOX")
        self.labels[message_id].add(label_id)
        self.filed.append(message_id)

    def check_repliable(self, original: FetchedMail) -> None:
        del original

    def send_reply(self, original: FetchedMail, draft: object) -> str:
        del draft
        self.sent.append(original.message_id)
        return "sent"


class Internet:
    """Anthropic judges a mail urgent when its text says URGENT; Telegram records what it is sent."""

    def __init__(self) -> None:
        self.model_calls = 0
        self.alerts: list[dict[str, Any]] = []
        self.other: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.anthropic.com":
            self.model_calls += 1
            content = json.loads(json.loads(request.content)["messages"][0]["content"])
            urgent = "URGENT" in content["text"]
            verdict = {
                "category": "Finance",
                "urgent": urgent,
                "reason": "asks for an answer" if urgent else "routine",
                "summary": "a summary",
                "confidence": 0.95,
            }
            return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(verdict)}]})
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": []})
        if method == "sendMessage":
            message = json.loads(request.content)
            (self.alerts if "reply_markup" in message else self.other).append(message)
            return httpx.Response(
                200, json={"ok": True, "result": {"message_id": 1000 + len(self.alerts + self.other)}}
            )
        return httpx.Response(200, json={"ok": True, "result": True})


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


def agent(  # noqa: PLR0913, PLR0917 - the fakes of the world are passed in, like in the wiring itself
    engine: AsyncEngine, gmail: StatefulGmail, internet: Internet, clock: Clock, tmp: Path, budget: int
) -> Runner:
    return build_runner(
        load_settings({**VALID, "DAILY_MODEL_BUDGET": str(budget)}),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(transport=httpx.MockTransport(internet)),
        mailbox=gmail,
        sender=gmail,
        own_address="marco@example.com",
        heartbeat=tmp / "heartbeat",
        now=clock.now,
        today=clock.today,
    )


async def seed_running_agent(engine: AsyncEngine) -> None:
    """The agent has run before: it holds a Gmail position, but nothing was ever caught up."""
    async with async_sessionmaker(engine).begin() as session:
        await session.execute(text("insert into poll_state (id, history_id) values (1, '100')"))


async def scalar(engine: AsyncEngine, sql: str) -> Any:
    async with engine.connect() as connection:
        return (await connection.execute(text(sql))).scalar_one()


async def run_cycles(run: Runner, count: int) -> None:
    for _ in range(count):
        await run.mail_cycle()


def old_inbox(gmail: StatefulGmail, count: int, urgent_from: int | None = None, urgent_count: int = 0) -> list[str]:
    """``count`` unread inbox mails, newest first; ``urgent_count`` of them urgent from index ``urgent_from``."""
    ids = [f"o{n:02d}" for n in range(count)]
    for n, mail_id in enumerate(ids):
        urgent = urgent_from is not None and urgent_from <= n < urgent_from + urgent_count
        gmail.add(mail_id, UNREAD_INBOX, "URGENT: please answer" if urgent else "an ordinary mail")
    return ids


async def test_given_75_unread_mails_and_a_small_budget_when_it_runs_for_days_then_everything_is_filed_safely(
    engine: AsyncEngine, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    gmail, internet, clock = StatefulGmail(), Internet(), Clock(DAY_ONE)
    all_old = old_inbox(gmail, 75, urgent_from=62, urgent_count=8)  # the 8 urgent mails are among the oldest 13
    gmail.add("read-1", {"INBOX"})  # already read: not ours
    gmail.add("read-2", {"INBOX"})
    gmail.add("archived-1", {"UNREAD"})  # unread, but not in the inbox: not ours
    untouched = {"read-1": {"INBOX"}, "read-2": {"INBOX"}, "archived-1": {"UNREAD"}}
    run = agent(engine, gmail, internet, clock, tmp_path, budget=100)  # room for 49 mails a day above the reserve
    await seed_running_agent(engine)

    # Day 1: the first cycle starts the catch-up; a new mail arrives in the middle and is handled first.
    await run.mail_cycle()
    gmail.arrive("new-1")
    await run.mail_cycle()
    assert "new-1" in gmail.filed  # new mail is never kept waiting by the catch-up
    await run_cycles(run, 4)
    day_one_calls = internet.model_calls
    assert 45 <= len(gmail.filed) <= 50
    assert day_one_calls <= 100 - BUDGET_RESERVE  # the reserve of 50 calls is untouched on day 1
    assert await scalar(engine, "select count(*) from catchup_state where finished_at is null") == 1

    # Day 2, in quiet hours (a new UTC day, so a fresh budget): the rest is filed, urgent alerts are held, not sent.
    clock.at = DAY_TWO_NIGHT
    await run_cycles(run, 4)
    assert set(gmail.filed) == {*all_old, "new-1"}  # every old unread mail has one label and left the inbox
    assert await scalar(engine, "select count(*) from catchup_state where finished_at is not null") == 1
    assert await scalar(engine, "select count(*) from alert where state = 'held'") == BACKLOG_ALERT_LIMIT
    assert internet.alerts == []  # quiet hours: nothing is sent at night

    # Day 3 morning: the held alerts go out, five in all, and the others wait for the overview.
    clock.at = DAY_THREE_MORNING
    await run_cycles(run, 2)
    assert len(internet.alerts) == BACKLOG_ALERT_LIMIT
    assert await scalar(engine, "select count(*) from mail_item where backlog and urgent") == 8
    assert (
        await scalar(engine, "select count(*) from alert a join mail_item m on m.id = a.mail_item_id where m.backlog")
        == 5
    )

    # Safety: nothing else was touched, nothing was sent or deleted, and no mail text leaked.
    for mail_id, labels in untouched.items():
        assert gmail.labels[mail_id] == labels
    assert gmail.sent == []
    assert all(len(gmail.labels[i] - UNREAD_INBOX) == 1 for i in all_old)  # exactly one new label each
    assert all("UNREAD" in gmail.labels[i] and "INBOX" not in gmail.labels[i] for i in all_old)
    assert SENTINEL not in caplog.text
    assert SENTINEL not in await scalar(engine, "select coalesce(string_agg(detail::text, ' '), '') from audit_log")


async def test_given_a_budget_of_200_when_75_old_mails_wait_then_one_day_is_enough(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    gmail, internet, clock = StatefulGmail(), Internet(), Clock(DAY_ONE)
    all_old = old_inbox(gmail, 75)
    run = agent(engine, gmail, internet, clock, tmp_path, budget=200)
    await seed_running_agent(engine)

    await run_cycles(run, 5)

    assert set(gmail.filed) == set(all_old)
    assert internet.model_calls == 75
    assert 200 - internet.model_calls >= BUDGET_RESERVE


async def test_given_a_restart_in_the_middle_when_it_resumes_then_no_mail_is_judged_twice_and_the_cutoff_stays(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    gmail, internet, clock = StatefulGmail(), Internet(), Clock(DAY_ONE)
    all_old = old_inbox(gmail, 30)
    await seed_running_agent(engine)
    first = agent(engine, gmail, internet, clock, tmp_path, budget=200)
    await first.mail_cycle()
    assert len(gmail.filed) == 20
    cutoff = await scalar(engine, "select started_at from catchup_state")

    clock.at = DAY_ONE + timedelta(minutes=5)
    second = agent(engine, gmail, internet, clock, tmp_path, budget=200)  # a new process, the same database
    await run_cycles(second, 3)

    assert sorted(gmail.filed) == sorted(all_old)
    assert internet.model_calls == 30
    assert await scalar(engine, "select started_at from catchup_state") == cutoff
    assert await scalar(engine, "select count(*) from catchup_state") == 1
