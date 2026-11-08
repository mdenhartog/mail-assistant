"""U-13: alert delivery (spec AC-3, AC-5, AC-12, AC-22, AC-26, AC-32)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from app.core.alert_state import AlertState
from app.core.alert_text import AlertMessage, AuthResults, MailMeta
from app.core.judgement import Judgement
from app.usecases.deliver_alerts import AlertDelivery, PendingAlert

DAYTIME = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # 13:00 in Amsterdam
NIGHT = datetime(2026, 11, 9, 22, 30, tzinfo=UTC)  # 23:30 in Amsterdam
JUDGEMENT = Judgement(category="Finance", urgent=True, reason="r", summary="s", confidence=0.9)


def pending(alert_id: str, state: AlertState = AlertState.OPEN) -> PendingAlert:
    meta = MailMeta(f"s{alert_id}@example.com", f"Subject {alert_id}", reply_to=None, has_attachment=False)
    return PendingAlert(alert_id, state, meta, JUDGEMENT, AuthResults("pass", "pass", "pass"))


@dataclass
class FakeStore:
    alerts: list[PendingAlert] = field(default_factory=list)
    sent: dict[str, int] = field(default_factory=dict)  # alert id -> telegram message id
    sent_at: list[datetime] = field(default_factory=list)
    audit: list[tuple[str, str]] = field(default_factory=list)
    released: list[str] = field(default_factory=list)

    async def held(self) -> list[PendingAlert]:
        return [a for a in self.alerts if a.state is AlertState.HELD and a.alert_id not in self.released]

    async def release(self, alert_id: str) -> None:
        self.released.append(alert_id)
        self.alerts = [
            PendingAlert(a.alert_id, AlertState.OPEN, a.meta, a.judgement, a.auth) if a.alert_id == alert_id else a
            for a in self.alerts
        ]

    async def unsent(self) -> list[PendingAlert]:
        return [a for a in self.alerts if a.state is AlertState.OPEN and a.alert_id not in self.sent]

    async def mark_sent(self, alert_id: str, telegram_message_id: int, *, at: datetime) -> None:
        self.sent[alert_id] = telegram_message_id
        self.sent_at.append(at)

    async def sent_since(self, since: datetime) -> int:
        return sum(1 for moment in self.sent_at if moment >= since)

    async def record_audit(self, kind: str, alert_id: str) -> None:
        self.audit.append((kind, alert_id))


class FakeOutbox:
    def __init__(self, *, fail_times: int = 0) -> None:
        self.messages: list[AlertMessage] = []
        self.fail_times = fail_times

    async def send(self, message: AlertMessage) -> int:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("telegram down")
        self.messages.append(message)
        return 1000 + len(self.messages)


def delivery(store: FakeStore, outbox: FakeOutbox, now: datetime = DAYTIME, cap: int = 5) -> AlertDelivery:
    return AlertDelivery(store, outbox, now=lambda: now, hourly_cap=cap)


async def test_given_an_open_alert_when_delivered_then_one_message_is_sent_and_its_id_stored() -> None:
    store, outbox = FakeStore([pending("1")]), FakeOutbox()

    await delivery(store, outbox).deliver_open_alerts()

    assert len(outbox.messages) == 1
    assert [b.data for b in outbox.messages[0].buttons] == ["reply:1", "later:1", "stop:1"]
    assert store.sent == {"1": 1001}


async def test_given_the_same_alert_on_the_next_run_when_delivered_then_nothing_is_sent() -> None:
    store, outbox = FakeStore([pending("1")]), FakeOutbox()
    run = delivery(store, outbox)

    await run.deliver_open_alerts()
    await run.deliver_open_alerts()

    assert len(outbox.messages) == 1


async def test_given_held_alerts_and_quiet_hours_have_not_ended_when_delivered_then_nothing_goes_out() -> None:
    store, outbox = FakeStore([pending("1", AlertState.HELD)]), FakeOutbox()

    await delivery(store, outbox, now=NIGHT).deliver_open_alerts()

    assert outbox.messages == []
    assert store.released == []


async def test_given_held_alerts_when_quiet_hours_end_then_they_go_out_together_in_one_batch() -> None:
    store = FakeStore([pending(str(i), AlertState.HELD) for i in range(3)])
    outbox = FakeOutbox()

    await delivery(store, outbox).deliver_open_alerts()

    assert store.released == ["0", "1", "2"]
    digest, *alerts = outbox.messages
    assert "while you were away" in digest.text
    assert digest.buttons == ()
    assert len(alerts) == 3
    assert set(store.sent) == {"0", "1", "2"}


async def test_given_a_single_held_alert_when_quiet_hours_end_then_only_the_alert_is_sent() -> None:
    store, outbox = FakeStore([pending("1", AlertState.HELD)]), FakeOutbox()

    await delivery(store, outbox).deliver_open_alerts()

    assert len(outbox.messages) == 1
    assert outbox.messages[0].buttons


async def test_given_more_alerts_than_the_hourly_cap_when_delivered_then_the_excess_is_one_summary() -> None:
    store = FakeStore([pending(str(i)) for i in range(7)])
    outbox = FakeOutbox()

    await delivery(store, outbox, cap=3).deliver_open_alerts()

    *singles, summary = outbox.messages
    assert len(singles) == 3
    assert all(m.buttons for m in singles)
    assert "4 more" in summary.text
    assert summary.buttons == ()
    assert set(store.sent) == {str(i) for i in range(7)}  # the excess is marked as delivered via the summary


async def test_given_alerts_already_sent_this_hour_when_delivered_then_the_cap_counts_them() -> None:
    store = FakeStore([pending("new1"), pending("new2")], sent_at=[DAYTIME - timedelta(minutes=10)] * 3)
    outbox = FakeOutbox()

    await delivery(store, outbox, cap=4).deliver_open_alerts()

    singles = [m for m in outbox.messages if m.buttons]
    assert len(singles) == 1  # 3 already sent, cap 4: one single, the other goes into the summary
    assert len(outbox.messages) == 2


async def test_given_old_deliveries_when_delivered_then_only_the_last_hour_counts() -> None:
    store = FakeStore([pending("1")], sent_at=[DAYTIME - timedelta(hours=2)] * 10)
    outbox = FakeOutbox()

    await delivery(store, outbox, cap=2).deliver_open_alerts()

    assert len(outbox.messages) == 1
    assert outbox.messages[0].buttons


async def test_given_telegram_fails_when_delivered_then_the_alert_stays_open_and_is_retried_without_duplicates() -> (
    None
):
    store, outbox = FakeStore([pending("1")]), FakeOutbox(fail_times=1)
    run = delivery(store, outbox)

    with pytest.raises(ConnectionError):
        await run.deliver_open_alerts()
    assert store.sent == {}

    await run.deliver_open_alerts()

    assert store.sent == {"1": 1001}
    assert len(outbox.messages) == 1


async def test_given_a_delivery_when_done_then_an_audit_record_without_a_body_is_written() -> None:
    store, outbox = FakeStore([pending("1"), pending("2")]), FakeOutbox()

    await delivery(store, outbox).deliver_open_alerts()

    assert store.audit == [("alert_sent", "1"), ("alert_sent", "2")]


async def test_given_nothing_to_deliver_when_run_then_nothing_is_sent() -> None:
    outbox = FakeOutbox()

    await delivery(FakeStore(), outbox).deliver_open_alerts()

    assert outbox.messages == []
