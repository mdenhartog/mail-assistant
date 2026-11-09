"""U-quiet-hours-14: adjustable quiet hours end to end, on a real PostgreSQL with the real router and a fake Telegram.

Nothing here starts the web backend: the agent reads and writes the settings table by itself (AC-35). The compose
profile without the backend service is U-quiet-hours-15; this is the integration-level proof of the same property.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.settings import load_settings
from app.wiring import build_runner
from tests.db.test_end_to_end import FakeGmail, FakeInternet, tap, typed
from tests.test_settings import VALID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.runner import Runner

START = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # 13:00 in Amsterdam, 23:00 in Sydney
STRANGER = 777


class RecordingInternet(FakeInternet):
    """The fake Anthropic and Telegram, remembering every Bot API method the agent called (except polling)."""

    def __init__(self) -> None:
        super().__init__()
        self.methods: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != "api.anthropic.com" and not request.url.path.endswith("getUpdates"):
            self.methods.append(request.url.path.rsplit("/", 1)[-1])
        return super().__call__(request)


@dataclass
class Agent:
    """The running agent: its runner, its fakes, a clock Marco can move and a counter for Telegram update ids."""

    runner: Runner
    gmail: FakeGmail
    internet: RecordingInternet
    engine: AsyncEngine
    now: datetime = START
    _update_id: int = field(default=0, init=False)

    def next_id(self) -> int:
        self._update_id += 1
        return self._update_id

    async def deliver(self, *updates: dict[str, Any]) -> None:
        """Telegram hands these updates over in one poll; the agent routes them."""
        self.internet.updates = [list(updates)]
        await self.runner.telegram_cycle()

    async def say(self, words: str) -> None:
        await self.deliver(typed(self.next_id(), words))

    async def press(self, label: str) -> None:
        """Tap the button with this label on the last message the agent sent."""
        keyboard = self.internet.messages[-1]["reply_markup"]["inline_keyboard"]
        [data] = [b["callback_data"] for row in keyboard for b in row if b["text"] == label]
        await self.deliver(tap(self.next_id(), data))

    def labels(self) -> list[str]:
        markup = self.internet.messages[-1].get("reply_markup", {"inline_keyboard": []})
        return [b["text"] for row in markup["inline_keyboard"] for b in row]

    async def scalar(self, sql: str) -> Any:
        async with self.engine.connect() as connection:
            return (await connection.execute(text(sql))).scalar_one_or_none()


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def agent(engine: AsyncEngine) -> Agent:
    gmail, internet = FakeGmail(), RecordingInternet()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    holder: list[Agent] = []
    runner = build_runner(
        load_settings(VALID),
        sessions=sessions,
        client=httpx.AsyncClient(transport=httpx.MockTransport(internet), timeout=httpx.Timeout(5.0)),
        mailbox=gmail,
        sender=gmail,
        own_address="marco@example.com",
        heartbeat=Path(mkdtemp()) / "heartbeat",
        now=lambda: holder[0].now,
    )
    holder.append(Agent(runner, gmail, internet, engine))
    async with sessions.begin() as session:
        await session.execute(text("insert into poll_state (id, history_id) values (1, '100')"))
    return holder[0]


def _alerts(agent: Agent) -> list[dict[str, Any]]:
    return [m for m in agent.internet.messages if "Invoice due Friday" in m["text"]]


async def _change_time_zone(agent: Agent, answer: str) -> None:
    await agent.say("/settings")
    await agent.press("Change time zone")
    await agent.say(answer)


# ---- AC-1: first-release behaviour with no row, and with no schema ----


async def test_given_an_empty_settings_table_when_the_agent_runs_then_the_first_release_behaviour_is_unchanged(
    agent: Agent,
) -> None:
    assert await agent.scalar("select count(*) from settings.schedule") == 0

    await agent.runner.mail_cycle()

    assert agent.gmail.filed == [("gm-1", "id:Assistant/Finance")]
    assert len(_alerts(agent)) == 1  # 13:00 in Amsterdam: not quiet hours, so the alert goes out at once
    assert len(agent.internet.messages) == 1  # and Marco is told nothing else
    assert await agent.scalar("select count(*) from settings.schedule") == 0  # reading writes no default row


async def test_given_the_settings_schema_is_absent_when_the_agent_runs_then_it_keeps_working_with_the_defaults(
    agent: Agent, engine: AsyncEngine
) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("drop schema settings cascade"))

    await agent.runner.mail_cycle()
    await agent.runner.mail_cycle()

    assert agent.gmail.filed == [("gm-1", "id:Assistant/Finance")]
    assert len(_alerts(agent)) == 1  # the defaults decided: the alert went out
    notices = [m for m in agent.internet.messages if "cannot use your saved settings" in m["text"]]
    assert len(notices) == 1  # C-9: Marco is told once per incident, naming the values in use
    assert "Europe/Amsterdam" in notices[0]["text"]
    assert "42P01" not in notices[0]["text"]  # the notice names the values in use, never the database error


# ---- AC-22: a Telegram change is used by the next run ----


async def test_given_a_time_zone_change_over_telegram_when_the_next_run_happens_then_quiet_hours_use_the_new_zone(
    agent: Agent,
) -> None:
    await _change_time_zone(agent, "Melbourne")  # 23:00 there: inside the default quiet hours 23:00 to 07:00

    stored = await agent.scalar("select zone || '|' || updated_via from settings.schedule")
    assert stored == "Australia/Melbourne|telegram"

    await agent.runner.mail_cycle()

    assert agent.gmail.filed == [("gm-1", "id:Assistant/Finance")]  # filing goes on
    assert _alerts(agent) == []  # but the alert is held until the quiet hours end in Melbourne
    assert await agent.scalar("select state from alert") == "held"


async def test_given_an_overview_time_change_over_telegram_when_the_next_run_happens_then_the_overview_uses_it(
    agent: Agent,
) -> None:
    await agent.runner.mail_cycle()  # 13:00 in Amsterdam, the overview is due at 18:00
    assert await agent.scalar("select count(*) from overview_log") == 0

    await agent.say("/settings")
    await agent.press("Change daily overview")
    await agent.say("12:30")
    await agent.runner.mail_cycle()

    assert await agent.scalar("select count(*) from overview_log") == 1  # 13:00 is past the new 12:30


async def test_given_a_remind_default_change_over_telegram_when_a_snooze_says_tomorrow_then_it_is_due_at_the_new_time(
    agent: Agent,
) -> None:
    await agent.runner.mail_cycle()
    [alert] = _alerts(agent)
    later = next(
        b["callback_data"]
        for row in alert["reply_markup"]["inline_keyboard"]
        for b in row
        if b["callback_data"].startswith("later:")
    )
    await agent.say("/settings")
    await agent.press("Change remind-me-later default")
    await agent.say("08:00")

    await agent.deliver(tap(agent.next_id(), later))
    await agent.say("tomorrow")

    due = await agent.scalar("select due_at from alert")
    assert due == datetime(2026, 11, 10, 7, 0, tzinfo=UTC)  # 08:00 in Amsterdam; the default 09:00 would be 08:00 UTC


# ---- AC-35: no backend process ----


async def test_given_a_row_written_by_another_process_when_the_agent_runs_then_it_reads_applies_and_changes_it(
    agent: Agent, engine: AsyncEngine
) -> None:
    async with engine.begin() as connection:  # what the web backend would do; here it is just SQL, no backend runs
        await connection.execute(
            text(
                "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, "
                "updated_by) values (1, 'Australia/Sydney', 1380, 420, 1080, 540, 'web', 'u1')"
            )
        )

    await agent.runner.mail_cycle()  # applied without a restart
    assert _alerts(agent) == []

    await agent.say("/settings")  # read
    assert "Australia/Sydney" in agent.internet.messages[-1]["text"]
    await agent.press("Change quiet hours")  # change
    await agent.say("00:00")
    await agent.say("06:00")

    row = await agent.scalar(
        "select quiet_start || ':' || quiet_end || ':' || version || ':' || updated_via from settings.schedule"
    )
    assert row == "0:360:2:telegram"


# ---- AC-3: a stranger ----


def _from_stranger(update: dict[str, Any]) -> dict[str, Any]:
    """The same update as the owner would send, but from another person in another private chat."""
    copy = json.loads(json.dumps(update))
    body = copy.get("message") or copy["callback_query"]
    body["from"]["id"] = STRANGER
    (body.get("chat") or body["message"]["chat"])["id"] = STRANGER
    return copy


async def test_given_a_stranger_sends_settings_and_taps_an_old_button_then_no_row_is_written_and_nothing_is_sent(
    agent: Agent,
) -> None:
    await agent.say("/settings")
    card = agent.internet.messages[-1]["reply_markup"]["inline_keyboard"]
    old_button = card[0][0]["callback_data"]
    sent_before = list(agent.internet.methods)
    messages_before = len(agent.internet.messages)

    await agent.deliver(
        _from_stranger(typed(agent.next_id(), "/settings")),
        _from_stranger(tap(agent.next_id(), old_button)),
        _from_stranger(typed(agent.next_id(), "Sydney")),
    )

    assert agent.internet.methods == sent_before  # not one Bot API call: no message, no callback answer
    assert len(agent.internet.messages) == messages_before
    assert await agent.scalar("select count(*) from settings.schedule") == 0
    assert await agent.scalar("select count(*) from settings.settings_change") == 0
    step = await agent.scalar("select step from conversation")
    assert step == "card"  # Marco's own question is untouched by the stranger's tap

    await agent.press("Change time zone")  # and it still works for Marco
    assert agent.labels() == ["Cancel"]
