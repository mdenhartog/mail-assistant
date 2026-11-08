"""U-16: the daily overview (spec AC-31)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING

from app.core import time_policy
from app.usecases.overview import FiledMail, OverviewService

if TYPE_CHECKING:
    import pytest

    from app.core.alert_text import AlertMessage

BEFORE = datetime(2026, 11, 9, 16, 59, tzinfo=UTC)  # 17:59 in Amsterdam
AFTER = datetime(2026, 11, 9, 17, 1, tzinfo=UTC)  # 18:01 in Amsterdam
NEXT_MORNING = datetime(2026, 11, 10, 6, 30, tzinfo=UTC)  # 07:30 in Amsterdam
TODAY = date(2026, 11, 9)


def filed(label: str, confidence: float = 0.9, sender: str = "a@example.com", subject: str = "Hi") -> FiledMail:
    return FiledMail(label=label, confidence=confidence, sender=sender, subject=subject)


@dataclass
class FakeStore:
    mails: list[FiledMail] = field(default_factory=list)
    sent_days: set[date] = field(default_factory=set)
    asked_since: list[datetime] = field(default_factory=list)

    async def filed_without_alert_since(self, since: datetime) -> list[FiledMail]:
        self.asked_since.append(since)
        return list(self.mails)

    async def overview_sent(self, day: date) -> bool:
        return day in self.sent_days

    async def mark_overview_sent(self, day: date) -> None:
        self.sent_days.add(day)


class FakeOutbox:
    def __init__(self) -> None:
        self.messages: list[AlertMessage] = []

    async def send(self, message: AlertMessage) -> int:
        self.messages.append(message)
        return len(self.messages)


def service(store: FakeStore, outbox: FakeOutbox, now: datetime) -> OverviewService:
    return OverviewService(store, outbox, now=lambda: now)


async def test_given_mails_filed_today_when_the_time_arrives_then_one_message_has_counts_and_unsure_mails() -> None:
    store = FakeStore(
        [
            filed("Assistant/Newsletters"),
            filed("Assistant/Newsletters"),
            filed("Assistant/Finance"),
            filed("Assistant/Other", confidence=0.3, sender="odd@example.com", subject="Strange mail"),
        ]
    )
    outbox = FakeOutbox()

    await service(store, outbox, AFTER).send_overview()

    assert len(outbox.messages) == 1
    text = outbox.messages[0].text
    assert "Newsletters" in text
    assert "2" in text
    assert "Finance" in text
    assert "odd@example.com" in text
    assert "Strange mail" in text
    assert outbox.messages[0].buttons == ()
    assert "Assistant/" not in text  # the prefix is noise for Marco


async def test_given_nothing_was_filed_when_the_time_arrives_then_no_message_is_sent() -> None:
    store, outbox = FakeStore(), FakeOutbox()

    await service(store, outbox, AFTER).send_overview()

    assert outbox.messages == []


async def test_given_the_overview_was_already_sent_today_when_run_again_then_nothing_is_sent() -> None:
    store, outbox = FakeStore([filed("Assistant/Finance")]), FakeOutbox()
    run = service(store, outbox, AFTER)

    await run.send_overview()
    await run.send_overview()

    assert len(outbox.messages) == 1
    assert TODAY in store.sent_days


async def test_given_it_is_before_the_overview_time_when_run_then_nothing_is_sent_yet() -> None:
    store, outbox = FakeStore([filed("Assistant/Finance")]), FakeOutbox()

    await service(store, outbox, BEFORE).send_overview()

    assert outbox.messages == []


async def test_given_the_overview_time_inside_quiet_hours_when_it_arrives_then_it_waits_until_they_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time_policy, "OVERVIEW_AT", time(23, 30))  # a future change, see INT-002
    store, outbox = FakeStore([filed("Assistant/Finance")]), FakeOutbox()
    late_evening = datetime(2026, 11, 9, 22, 45, tzinfo=UTC)  # 23:45 local

    await service(store, outbox, late_evening).send_overview()
    assert outbox.messages == []

    await service(store, outbox, NEXT_MORNING).send_overview()

    assert len(outbox.messages) == 1
    assert TODAY in store.sent_days


async def test_given_a_quiet_day_when_the_time_arrives_then_it_is_remembered_so_a_late_mail_does_not_trigger_one() -> (
    None
):
    store, outbox = FakeStore(), FakeOutbox()
    await service(store, outbox, AFTER).send_overview()

    store.mails.append(filed("Assistant/Finance"))
    await service(store, outbox, AFTER).send_overview()

    assert outbox.messages == []


async def test_given_many_unsure_mails_with_growing_text_when_built_then_the_list_is_shortened_to_fit() -> None:
    mails = [filed("Assistant/Other", 0.1, sender="&" * 60, subject="&" * 80) for _ in range(30)]

    store, outbox = FakeStore(mails), FakeOutbox()
    await service(store, outbox, AFTER).send_overview()

    text = outbox.messages[0].text
    assert len(text) <= 4096
    assert "more" in text
    assert "&amp" not in text.replace("&amp;", "")


async def test_given_hostile_text_and_many_mails_when_built_then_it_is_escaped_and_fits_one_message() -> None:
    mails = [filed("Assistant/Other", 0.1, sender="<b>x</b>@example.com", subject="<a href='x'>y</a>" * 20)] * 300

    store, outbox = FakeStore(mails), FakeOutbox()
    await service(store, outbox, AFTER).send_overview()

    text = outbox.messages[0].text
    assert len(text) <= 4096
    assert "<a href" not in text
    assert "<b>x</b>" not in text
