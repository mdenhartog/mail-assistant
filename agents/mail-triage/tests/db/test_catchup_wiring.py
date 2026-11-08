"""U-backlog-10: the catch-up runs inside the real wiring (INT-003; AC-B4, AC-B7, AC-B15)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.adapters.gmail_read import FetchedMail
from app.settings import load_settings
from app.wiring import build_runner
from tests.db.test_end_to_end import FakeGmail, FakeInternet
from tests.test_settings import VALID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from app.runner import Runner

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # 13:00 in Amsterdam: not quiet hours


def old_mail(message_id: str) -> FetchedMail:
    return FetchedMail(
        message_id=message_id,
        thread_id=f"t-{message_id}",
        sender="shop@example.com",
        reply_to=None,
        subject="Old unread mail",
        text="This was already in the inbox before the agent started.",
        has_attachment=False,
        headers={},
        labels=frozenset({"INBOX", "UNREAD"}),
    )


class GmailWithOldMail(FakeGmail):
    """The fake from the end-to-end test, plus unread mail that was in the inbox before the agent started."""

    def __init__(self, old_ids: list[str]) -> None:
        super().__init__()
        self.old = {i: old_mail(i) for i in old_ids}
        self.listed_with: list[datetime] = []

    def list_new(self, history_id: str | None) -> tuple[list[str], str]:
        return [], "200"  # no new mail in these tests

    def list_unread_before(self, cutoff: datetime) -> list[str]:
        self.listed_with.append(cutoff)
        return [i for i in self.old if i not in {m for m, _ in self.filed}]

    def fetch(self, message_id: str) -> FetchedMail:
        return self.old[message_id]


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


def _runner(engine: AsyncEngine, gmail: FakeGmail, internet: FakeInternet, tmp_path: Path, **overrides: str) -> Runner:
    return build_runner(
        load_settings({**VALID, **overrides}),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(transport=httpx.MockTransport(internet)),
        mailbox=gmail,
        sender=gmail,
        own_address="marco@example.com",
        heartbeat=tmp_path / "heartbeat",
        now=lambda: NOW,
    )


async def _seed_history(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine).begin() as session:
        await session.execute(text("insert into poll_state (id, history_id) values (1, '100')"))


async def test_given_a_running_installation_without_catch_up_state_when_a_cycle_runs_then_the_catch_up_starts_by_itself(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    gmail, internet = GmailWithOldMail(["old-1", "old-2"]), FakeInternet()
    run = _runner(engine, gmail, internet, tmp_path)
    await _seed_history(engine)  # the agent has been running before: a position, but no catch-up row

    await run.mail_cycle()

    assert sorted(m for m, _ in gmail.filed) == ["old-1", "old-2"]
    assert gmail.listed_with == [NOW]  # the cut-off is the moment the catch-up started
    async with engine.connect() as connection:
        row = (await connection.execute(text("select started_at, finished_at from catchup_state"))).one()
        flagged = (await connection.execute(text("select count(*) from mail_item where backlog"))).scalar_one()
    assert row.started_at == NOW
    assert row.finished_at == NOW
    assert flagged == 2


async def test_given_a_budget_of_52_when_new_and_old_mail_wait_then_the_budget_is_shared_and_the_reserve_holds(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    gmail, internet = GmailWithOldMail(["old-1"]), FakeInternet()
    gmail.mail = FakeGmail().mail  # the urgent mail of the end-to-end test is the new mail
    gmail.old = {"gm-1": gmail.mail, "old-1": old_mail("old-1")}
    gmail.list_new = lambda history_id: (["gm-1"], "200")  # type: ignore[method-assign]
    gmail.list_unread_before = lambda cutoff: ["old-1"]  # type: ignore[method-assign]
    run = _runner(engine, gmail, internet, tmp_path, DAILY_MODEL_BUDGET="52")
    await _seed_history(engine)

    await run.mail_cycle()

    assert [m for m, _ in gmail.filed] == ["gm-1"]  # new mail first, and it used 1 call: 51 are left
    assert internet.model_calls == 1  # 51 is below the reserve of 50 plus 2: the old mail waits
