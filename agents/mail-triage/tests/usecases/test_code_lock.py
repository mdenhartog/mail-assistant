"""U-web-settings-55 (W-13, W-15, RT-07, SEC-03): 15 wrong codes in 24 hours set the web lock, once, with one notice."""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from app.usecases.code_alert import CodeAlert
from schedule_policy.testing import FakeClock
from tests.usecases.fakes_code_alert import FakeEvents, SpyChat
from tests.usecases.fakes_web_actions import FakeLock

HOUR = timedelta(hours=1)


class Setup:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.events = FakeEvents()
        self.chat = SpyChat()
        self.lock = FakeLock()
        self.alert = CodeAlert(self.events, self.lock, self.chat)

    def refused(self, ago: timedelta, count: int = 1) -> None:
        self.events.add(self.clock.now() - ago, "code_refused", count)

    def spread(self, total: int) -> None:
        """``total`` wrong codes as single events, an hour apart (never five inside ten minutes)."""
        for hour in range(total):
            self.refused(hour * HOUR + timedelta(minutes=1))

    async def run(self) -> None:
        await self.alert.run(self.clock.now())


# ---- criterion 1: 15 in 24 hours -----


async def test_given_15_wrong_codes_in_24_hours_when_the_agent_runs_then_the_lock_is_set_and_one_notice_is_sent() -> (
    None
):
    setup = Setup()
    setup.spread(15)  # the oldest is 14 hours 1 minute old

    await setup.run()

    assert setup.lock.locked_at == setup.clock.now()
    assert setup.lock.sets == 1
    assert len(setup.chat.said) == 1
    notice = setup.chat.said[0]
    assert "15 wrong" in notice
    assert "2026-01-01 12:00" in notice
    assert "/web_unlock" in notice


async def test_given_one_row_with_count_15_when_the_agent_runs_then_the_lock_is_set() -> None:
    setup = Setup()
    setup.refused(timedelta(minutes=1), count=15)  # fifteen wrong codes in one minute are ONE row

    await setup.run()

    assert setup.lock.sets == 1
    assert len(setup.chat.said) == 1  # the lock notice replaces the 5-in-10-minutes notice of the same run
    assert "15 wrong" in setup.chat.said[0]


# ---- criterion 2: 14, or 15 over 24 hours 1 second -----


async def test_given_14_wrong_codes_when_the_agent_runs_then_nothing_changes() -> None:
    setup = Setup()
    setup.spread(14)

    await setup.run()

    assert setup.lock.calls == 0
    assert setup.chat.said == []


async def test_given_15_wrong_codes_over_24_hours_1_second_when_the_agent_runs_then_nothing_changes() -> None:
    setup = Setup()
    setup.refused(timedelta(hours=24, seconds=1))
    setup.spread(14)

    await setup.run()

    assert setup.lock.calls == 0
    assert setup.chat.said == []


async def test_given_an_event_exactly_24_hours_old_when_the_agent_runs_then_it_does_not_count() -> None:
    setup = Setup()
    setup.refused(timedelta(hours=24))
    setup.spread(14)

    await setup.run()
    assert setup.lock.calls == 0
    setup.refused(timedelta(hours=23, minutes=59, seconds=59))
    await setup.run()

    assert setup.lock.sets == 1


async def test_given_15_events_of_other_kinds_when_the_agent_runs_then_the_lock_stays_open() -> None:
    setup = Setup()
    for kind in ("rate_limited", "csrf_refused", "mail_failed", "code_request_refused"):
        setup.events.add(setup.clock.now() - HOUR, kind, 50)

    await setup.run()

    assert setup.lock.calls == 0
    assert setup.chat.said == []


# ---- criterion 3: once -----


async def test_given_the_lock_was_set_when_the_agent_runs_again_then_no_second_write_and_no_second_notice() -> None:
    setup = Setup()
    setup.spread(15)
    await setup.run()

    setup.clock.advance(timedelta(minutes=30))
    setup.refused(timedelta(0), count=40)
    await setup.run()
    setup.clock.advance(timedelta(hours=2))
    await setup.run()

    assert setup.lock.calls == 1
    assert len(setup.chat.said) == 1


async def test_given_marco_locked_it_when_the_agent_runs_then_it_writes_nothing_and_says_nothing() -> None:
    setup = Setup()
    setup.spread(15)
    await setup.lock.lock(setup.clock.now())  # a Telegram button or /web_lock set it
    setup.lock.calls = 0

    await setup.run()

    assert setup.lock.calls == 0
    assert setup.chat.said == []


async def test_given_a_locked_sign_in_when_the_agent_runs_then_the_wrong_code_notice_stays_silent() -> None:
    setup = Setup()
    await setup.lock.lock(setup.clock.now())
    setup.refused(timedelta(minutes=1), count=9)

    await setup.run()

    assert setup.chat.said == []


# ---- criterion 4: /web_unlock does not bring the old events back -----


async def test_given_an_unlock_when_the_agent_runs_then_the_old_events_do_not_set_the_lock_again() -> None:
    setup = Setup()
    setup.spread(15)
    await setup.run()  # locks and says so

    await setup.lock.unlock()  # /web_unlock
    setup.clock.advance(timedelta(minutes=1))
    await setup.run()
    setup.clock.advance(timedelta(hours=3))
    await setup.run()

    assert setup.lock.sets == 1
    assert len(setup.chat.said) == 1


async def test_given_an_unlock_when_15_new_wrong_codes_come_then_the_lock_is_set_again() -> None:
    setup = Setup()
    setup.spread(15)
    await setup.run()
    await setup.lock.unlock()
    setup.clock.advance(timedelta(minutes=10))
    for minutes in range(14):
        setup.refused(timedelta(minutes=minutes))  # new events only (they are inside 10 minutes: one 5-in-10 notice)

    await setup.run()
    assert setup.lock.sets == 1  # 14 new ones are not enough
    setup.refused(timedelta(0))
    await setup.run()

    assert setup.lock.sets == 2
    assert "15 wrong" in setup.chat.said[-1]


async def test_given_an_unlock_when_the_agent_runs_then_the_old_events_do_not_alert_after_5_in_10_minutes_either() -> (
    None
):
    setup = Setup()
    setup.refused(timedelta(minutes=2), count=15)
    await setup.run()
    await setup.lock.unlock()
    setup.clock.advance(timedelta(minutes=1))

    await setup.run()

    assert len(setup.chat.said) == 1


async def test_given_events_before_a_lock_that_marco_set_when_it_is_lifted_then_they_stay_spent() -> None:
    setup = Setup()
    setup.spread(15)
    await setup.lock.lock(setup.clock.now())
    await setup.run()  # sees the lock and spends the events
    await setup.lock.unlock()

    await setup.run()

    assert setup.lock.sets == 1
    assert setup.chat.said == []


# ---- a notice that could not be sent -----


async def test_given_a_failed_notice_when_the_agent_runs_again_then_it_is_sent_without_a_second_lock_write() -> None:
    setup = Setup()
    setup.spread(15)
    setup.chat.fail_next = True

    with pytest.raises(RuntimeError):
        await setup.run()
    assert setup.lock.locked_at is not None  # the lock holds even when Telegram does not answer
    await setup.run()

    assert setup.lock.calls == 1
    assert len(setup.chat.said) == 1
    assert "15 wrong" in setup.chat.said[0]


async def test_given_a_failed_notice_and_an_unlock_when_the_agent_runs_then_the_old_notice_is_dropped() -> None:
    setup = Setup()
    setup.spread(15)
    setup.chat.fail_next = True
    with pytest.raises(RuntimeError):
        await setup.run()
    await setup.lock.unlock()

    await setup.run()

    assert setup.chat.said == []


async def test_given_a_lock_that_cannot_be_written_when_the_agent_runs_then_no_notice_claims_it_is_set() -> None:
    setup = Setup()
    setup.spread(15)
    setup.lock.fail = True

    with pytest.raises(RuntimeError):
        await setup.run()

    assert setup.chat.said == []


# ---- criterion 7: nothing identifying -----


async def test_given_the_lock_notice_and_a_failure_when_captured_then_no_digest_username_or_code_appears(
    caplog: pytest.LogCaptureFixture,
) -> None:
    setup = Setup()
    setup.refused(timedelta(minutes=1), count=20)
    caplog.set_level(logging.DEBUG)
    setup.chat.fail_next = True

    with pytest.raises(RuntimeError):
        await setup.run()
    await setup.run()

    seen = caplog.text + " ".join(setup.chat.said)
    for canary in ("CANARYUSER", "CANARYDIGEST", "123456"):
        assert canary not in seen
    assert "20 wrong" in setup.chat.said[0]
    assert not caplog.records
