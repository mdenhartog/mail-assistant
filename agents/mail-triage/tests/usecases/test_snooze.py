"""U-15: snooze and close commands (spec AC-9, AC-10, AC-32)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from app.core.alert_state import AlertState
from app.core.time_policy import snooze_due
from app.usecases.snooze import SnoozeService

DAYTIME = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # 13:00 in Amsterdam
NIGHT = datetime(2026, 11, 9, 22, 30, tzinfo=UTC)  # 23:30 in Amsterdam


@dataclass
class Row:
    state: AlertState
    due_at: datetime | None = None
    resend: bool = False


@dataclass
class FakeStore:
    rows: dict[str, Row] = field(default_factory=dict)
    saves: int = 0
    audit: list[tuple[str, str]] = field(default_factory=list)

    async def state_of(self, alert_id: str) -> AlertState | None:
        row = self.rows.get(alert_id)
        return row.state if row else None

    async def set_state(
        self, alert_id: str, state: AlertState, *, due_at: datetime | None = None, resend: bool = False
    ) -> None:
        self.saves += 1
        self.rows[alert_id] = Row(state, due_at, resend)

    async def due_snoozed(self, now: datetime) -> list[str]:
        return [i for i, r in self.rows.items() if r.state is AlertState.SNOOZED and r.due_at and r.due_at <= now]

    async def record_audit(self, kind: str, alert_id: str) -> None:
        self.audit.append((kind, alert_id))


class FakeSay:
    def __init__(self) -> None:
        self.said: list[str] = []

    async def say(self, text: str) -> None:
        self.said.append(text)


def service(store: FakeStore, say: FakeSay, now: datetime = DAYTIME) -> SnoozeService:
    return SnoozeService(store, say, now=lambda: now)


async def test_given_an_alert_when_snoozed_for_three_hours_then_it_is_snoozed_until_then() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()

    await service(store, say).snooze("1", "3")

    assert store.rows["1"].state is AlertState.SNOOZED
    assert store.rows["1"].due_at == DAYTIME + timedelta(hours=3)
    assert store.audit == [("alert_snoozed", "1")]


async def test_given_a_snoozed_alert_when_not_yet_due_then_nothing_is_released() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()
    await service(store, say).snooze("1", "3")

    await service(store, say, now=DAYTIME + timedelta(hours=2)).release_due()

    assert store.rows["1"].state is AlertState.SNOOZED


async def test_given_tomorrow_when_snoozed_then_the_due_time_follows_the_time_policy() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()

    await service(store, say).snooze("1", "Tomorrow")

    assert store.rows["1"].due_at == snooze_due(DAYTIME, "tomorrow")


async def test_given_the_due_time_passes_when_released_then_the_alert_is_open_once_and_marked_for_resending() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()
    await service(store, say).snooze("1", "3")
    later = service(store, say, now=DAYTIME + timedelta(hours=3, minutes=1))

    released = await later.release_due()
    again = await later.release_due()

    assert released == ["1"]
    assert again == []
    assert store.rows["1"].state is AlertState.OPEN
    assert store.rows["1"].resend is True


async def test_given_a_due_time_inside_quiet_hours_when_released_then_the_alert_is_held() -> None:
    store, say = FakeStore({"1": Row(AlertState.SNOOZED, due_at=NIGHT - timedelta(hours=1))}), FakeSay()

    await service(store, say, now=NIGHT).release_due()

    assert store.rows["1"].state is AlertState.HELD
    assert store.rows["1"].resend is True


@pytest.mark.parametrize("text", ["abc", "", "0", "-3", "169", "500", "1.5", "3 hours please", "tomorow"])
async def test_given_invalid_input_when_snoozing_then_marco_is_asked_again_and_nothing_changes(text: str) -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()

    await service(store, say).snooze("1", text)

    assert store.rows["1"].state is AlertState.OPEN
    assert store.saves == 0
    assert len(say.said) == 1
    assert "1" in say.said[0]
    assert "tomorrow" in say.said[0]


async def test_given_no_more_reminders_when_chosen_then_the_alert_is_closed_for_good() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()

    await service(store, say).close("1")

    assert store.rows["1"].state is AlertState.CLOSED
    assert store.audit == [("alert_closed", "1")]


async def test_given_a_snoozed_alert_when_closed_then_it_never_comes_back() -> None:
    store, say = FakeStore({"1": Row(AlertState.SNOOZED, due_at=DAYTIME)}), FakeSay()

    await service(store, say).close("1")
    released = await service(store, say, now=DAYTIME + timedelta(days=1)).release_due()

    assert released == []
    assert store.rows["1"].state is AlertState.CLOSED


@pytest.mark.parametrize("action", ["snooze", "close"])
async def test_given_an_alert_that_cannot_take_the_action_when_asked_then_marco_is_told_and_nothing_changes(
    action: str,
) -> None:
    store, say = FakeStore({"1": Row(AlertState.CLOSED)}), FakeSay()
    run = service(store, say)

    await (run.snooze("1", "3") if action == "snooze" else run.close("1"))

    assert store.saves == 0
    assert say.said == ["That alert is no longer open."]


async def test_given_an_unknown_alert_when_asked_then_marco_is_told() -> None:
    store, say = FakeStore(), FakeSay()

    await service(store, say).close("nope")

    assert say.said == ["That alert is no longer open."]
