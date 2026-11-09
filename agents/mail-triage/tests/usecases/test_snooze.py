"""U-15: snooze and close commands (spec AC-9, AC-10, AC-32)."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta

import pytest

from app.core.alert_state import AlertState
from app.core.time_policy import remind_due
from app.usecases.snooze import SnoozeService
from schedule_policy.policy import DEFAULT_POLICY
from tests.usecases.fakes_policy import FakePolicySource

DAYTIME = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # 13:00 in Amsterdam
NIGHT = datetime(2026, 11, 9, 22, 30, tzinfo=UTC)  # 23:30 in Amsterdam


@dataclass
class Row:
    state: AlertState
    due_at: datetime | None = None
    resend: bool = False
    release_at: datetime | None = None


@dataclass
class FakeStore:
    rows: dict[str, Row] = field(default_factory=dict)
    saves: int = 0
    audit: list[tuple[str, str]] = field(default_factory=list)

    async def state_of(self, alert_id: str) -> AlertState | None:
        row = self.rows.get(alert_id)
        return row.state if row else None

    async def set_state(
        self,
        alert_id: str,
        state: AlertState,
        *,
        due_at: datetime | None = None,
        resend: bool = False,
        release_at: datetime | None = None,
    ) -> None:
        self.saves += 1
        self.rows[alert_id] = Row(state, due_at, resend, release_at)

    async def due_snoozed(self, now: datetime) -> list[str]:
        return [i for i, r in self.rows.items() if r.state is AlertState.SNOOZED and r.due_at and r.due_at <= now]

    async def record_audit(self, kind: str, alert_id: str) -> None:
        self.audit.append((kind, alert_id))


class FakeSay:
    def __init__(self) -> None:
        self.said: list[str] = []

    async def say(self, text: str) -> None:
        self.said.append(text)


def service(
    store: FakeStore, say: FakeSay, now: datetime = DAYTIME, source: FakePolicySource | None = None
) -> SnoozeService:
    return SnoozeService(store, say, now=lambda: now, policy=source or FakePolicySource(DEFAULT_POLICY))


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

    assert store.rows["1"].due_at == remind_due(DAYTIME, "tomorrow", DEFAULT_POLICY)


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


# ---- U-quiet-hours-12: one policy snapshot per operation, due moments stay put (AC-24, AC-26) ----------------------

NEW_YORK = replace(DEFAULT_POLICY, zone="America/New_York")
AFTERNOON_QUIET = replace(DEFAULT_POLICY, quiet_start=time(16, 0), quiet_end=time(20, 0))  # 15:00-19:00 UTC in winter


async def test_given_a_stored_zone_change_when_snoozed_until_tomorrow_then_the_new_zone_sets_the_due_moment() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()

    await service(store, say, source=FakePolicySource(NEW_YORK)).snooze("1", "tomorrow")

    assert store.rows["1"].due_at == datetime(2026, 11, 10, 14, 0, tzinfo=UTC)  # 09:00 in New York


async def test_given_a_policy_source_that_changes_on_its_second_call_when_snoozing_then_it_is_asked_once() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()
    source = FakePolicySource(DEFAULT_POLICY, NEW_YORK)

    await service(store, say, source=source).snooze("1", "tomorrow")

    assert source.calls == 1
    assert store.rows["1"].due_at == remind_due(DAYTIME, "tomorrow", DEFAULT_POLICY)


async def test_given_a_snoozed_alert_when_the_settings_change_then_its_due_moment_does_not_move() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()
    source = FakePolicySource(DEFAULT_POLICY)
    await service(store, say, source=source).snooze("1", "3")
    due = store.rows["1"].due_at
    source.set(NEW_YORK)

    early = await service(store, say, now=DAYTIME + timedelta(hours=2, minutes=59), source=source).release_due()
    on_time = await service(store, say, now=DAYTIME + timedelta(hours=3), source=source).release_due()

    assert due == DAYTIME + timedelta(hours=3)
    assert early == []
    assert on_time == ["1"]


async def test_given_a_snooze_due_inside_the_new_quiet_hours_when_released_then_it_is_held_until_that_quiet_end() -> None:
    store, say = FakeStore({"1": Row(AlertState.OPEN)}), FakeSay()
    await service(store, say).snooze("1", "3")  # due 15:00 UTC, 16:00 in Amsterdam
    source = FakePolicySource(AFTERNOON_QUIET)  # then quiet hours become 16:00-20:00

    await service(store, say, now=DAYTIME + timedelta(hours=3, minutes=1), source=source).release_due()

    row = store.rows["1"]
    assert (row.state, row.resend) == (AlertState.HELD, True)
    assert row.release_at == datetime(2026, 11, 9, 19, 0, tzinfo=UTC)  # 20:00 in Amsterdam


async def test_given_a_snooze_due_outside_quiet_hours_when_released_then_it_is_open_without_a_release_moment() -> None:
    store, say = FakeStore({"1": Row(AlertState.SNOOZED, due_at=DAYTIME)}), FakeSay()

    await service(store, say).release_due()

    assert store.rows["1"] == Row(AlertState.OPEN, None, True, None)


async def test_given_no_quiet_hours_configured_when_a_snooze_falls_due_at_night_then_it_is_open() -> None:
    no_quiet = replace(DEFAULT_POLICY, quiet_start=time(7, 0), quiet_end=time(7, 0))
    store, say = FakeStore({"1": Row(AlertState.SNOOZED, due_at=NIGHT)}), FakeSay()

    await service(store, say, now=NIGHT, source=FakePolicySource(no_quiet)).release_due()

    assert store.rows["1"] == Row(AlertState.OPEN, None, True, None)


async def test_given_a_policy_source_that_changes_on_its_second_call_when_releasing_then_it_is_asked_once() -> None:
    rows = {"1": Row(AlertState.SNOOZED, due_at=NIGHT), "2": Row(AlertState.SNOOZED, due_at=NIGHT)}
    store, say = FakeStore(rows), FakeSay()
    source = FakePolicySource(DEFAULT_POLICY, NEW_YORK)  # at 22:30 UTC: quiet in Amsterdam, 17:30 in New York

    await service(store, say, now=NIGHT, source=source).release_due()

    assert source.calls == 1
    assert [store.rows[i].state for i in ("1", "2")] == [AlertState.HELD, AlertState.HELD]
    assert store.rows["1"].release_at == store.rows["2"].release_at == datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
