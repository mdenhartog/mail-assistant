"""U-quiet-hours-11 on a real PostgreSQL: the confirmation and Undo with the real store and conversation row."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.pg_conversation import ConversationStore
from app.db.pg_settings_store import PgSettingsStore
from app.db.pg_update_cursor import PgUpdateCursor
from app.usecases.dispatch import CommandRouter
from app.usecases.settings_dialog import SettingsDialog
from schedule_policy.policy import DEFAULT_POLICY
from schedule_policy.testing import FakeClock, make_policy
from tests.db.test_settings_dialog_pg import engine  # noqa: F401  # the fixture of the U-09 database tests
from tests.usecases.test_dispatch import FakeReply, FakeSnooze, FakeStore, button
from tests.usecases.test_dispatch import text as typed
from tests.usecases.test_settings_dialog import RecordingChat

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

USER = 4242
EVENING = datetime(2026, 11, 9, 22, 5, tzinfo=UTC)


class Agent:
    """One 'run' of the agent: a router, a dialogue and a chat over the same database. A restart makes a new one."""

    def __init__(self, pg: AsyncEngine, clock: FakeClock) -> None:
        sessions = async_sessionmaker(pg, expire_on_commit=False)
        self.chat = RecordingChat()
        self.store = PgSettingsStore(sessions)
        conversations = ConversationStore(sessions, clock.now)
        self.router = CommandRouter(
            FakeReply(), FakeSnooze(), FakeStore(), self.chat, conversations, PgUpdateCursor(sessions)
        )
        dialog = SettingsDialog(self.store, self.chat, conversations, USER, clock.now, lambda: DEFAULT_POLICY)
        self.router.register(dialog)

    async def press(self, label: str) -> None:
        matches = [b for b in self.chat.sent[-1].buttons if b.label == label]
        assert len(matches) == 1, [b.label for b in self.chat.sent[-1].buttons]
        await self.router.handle(button(matches[0].data))

    async def change_zone_to_new_york(self) -> None:
        await self.router.handle(typed("/settings"))
        await self.press("Change time zone")
        await self.router.handle(typed("New York"))


async def _audit_rows(pg: AsyncEngine) -> list[tuple[str, str]]:
    query = text(
        "select new ->> 'zone', new ->> 'version' from settings.settings_change order by (new ->> 'version')::int"
    )
    async with pg.connect() as connection:
        return [(row[0], row[1]) for row in (await connection.execute(query)).all()]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(EVENING)


async def test_given_a_zone_change_when_undone_after_a_restart_and_20_minutes_then_the_row_and_audit_trail_show_it(
    engine: AsyncEngine,  # noqa: F811
    clock: FakeClock,
) -> None:
    first = Agent(engine, clock)
    await first.store.write(make_policy(), 0, "web", "seed")
    await first.change_zone_to_new_york()
    assert first.chat.sent[-1].text.splitlines()[1] == "Time zone: America/New_York (UTC-5)"
    clock.advance(timedelta(minutes=20))

    restarted = Agent(engine, clock)
    await restarted.chat.send(first.chat.sent[-1])  # the confirmation message Marco still sees
    await restarted.press("Undo")

    stored = await restarted.store.read()
    assert stored is not None
    assert (stored.policy, stored.version, stored.updated_via, stored.updated_by) == (
        make_policy(),
        3,
        "telegram",
        str(USER),
    )
    assert restarted.chat.sent[-1].text.splitlines()[0] == "Undone. The previous values are back."
    assert await _audit_rows(engine) == [
        ("Europe/Amsterdam", "1"),
        ("America/New_York", "2"),
        ("Europe/Amsterdam", "3"),
    ]


async def test_given_another_writer_after_the_change_when_undo_is_tapped_then_the_other_value_stays(
    engine: AsyncEngine,  # noqa: F811
    clock: FakeClock,
) -> None:
    agent = Agent(engine, clock)
    await agent.store.write(make_policy(), 0, "web", "seed")
    await agent.change_zone_to_new_york()
    other = make_policy(zone="Asia/Tokyo")
    await agent.store.write(other, 2, "web", "someone")

    await agent.press("Undo")

    stored = await agent.store.read()
    assert stored is not None
    assert (stored.policy, stored.version) == (other, 3)
    assert agent.chat.sent[-1].text.startswith("The settings changed since then")
