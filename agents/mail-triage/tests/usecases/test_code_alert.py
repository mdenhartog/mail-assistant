"""U-web-settings-48 (AC-20, W-13, W-15, SEC-04): one Telegram notice after 5 wrong or expired codes in 10 minutes."""

from __future__ import annotations

import ast
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from app.usecases.code_alert import CodeAlert
from schedule_policy.testing import FakeClock
from tests.usecases.fakes_code_alert import FakeEvents, SpyChat

APP = Path(__file__).resolve().parents[2] / "app"
MINUTE = timedelta(minutes=1)


class Setup:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.events = FakeEvents()
        self.chat = SpyChat()
        self.alert = CodeAlert(self.events, self.chat)

    def refused(self, ago: timedelta, count: int = 1) -> None:
        self.events.add(self.clock.now() - ago, "code_refused", count)

    async def run(self) -> None:
        await self.alert.run(self.clock.now())


# ---- criterion 1: five wrong codes, one notice ----------


async def test_given_5_code_refused_events_in_10_minutes_when_the_agent_runs_then_one_notice_with_count_and_time() -> (
    None
):
    setup = Setup()
    for minutes in range(5):
        setup.refused(minutes * MINUTE)

    await setup.run()

    assert len(setup.chat.said) == 1
    assert "5 wrong" in setup.chat.said[0]
    assert "2026-01-01 12:00" in setup.chat.said[0]


async def test_given_one_row_with_count_5_when_the_agent_runs_then_it_alerts_like_5_rows() -> None:
    setup = Setup()
    setup.refused(timedelta(seconds=30), count=5)  # five wrong codes in one minute are ONE row (SEC-04)

    await setup.run()

    assert len(setup.chat.said) == 1
    assert "5 wrong" in setup.chat.said[0]


async def test_given_rows_with_counts_2_2_and_1_when_the_agent_runs_then_the_notice_names_the_sum() -> None:
    setup = Setup()
    for ago, count in ((1 * MINUTE, 2), (4 * MINUTE, 2), (9 * MINUTE, 1)):
        setup.refused(ago, count)

    await setup.run()

    assert len(setup.chat.said) == 1
    assert "5 wrong" in setup.chat.said[0]


# ---- criterion 2: below the line, or too slow ----------


async def test_given_4_events_when_the_agent_runs_then_there_is_no_notice() -> None:
    setup = Setup()
    for minutes in range(4):
        setup.refused(minutes * MINUTE)

    await setup.run()

    assert setup.chat.said == []


async def test_given_a_row_with_count_4_when_the_agent_runs_then_there_is_no_notice() -> None:
    setup = Setup()
    setup.refused(MINUTE, count=4)

    await setup.run()

    assert setup.chat.said == []


async def test_given_5_events_spread_over_10_minutes_1_second_when_the_agent_runs_then_there_is_no_notice() -> None:
    setup = Setup()
    setup.refused(timedelta(minutes=10, seconds=1))
    for minutes in (7, 5, 3, 1):
        setup.refused(minutes * MINUTE)

    await setup.run()

    assert setup.chat.said == []


async def test_given_an_event_exactly_10_minutes_old_when_the_agent_runs_then_it_does_not_count() -> None:
    setup = Setup()
    setup.refused(timedelta(minutes=10))  # the window is "newer than 10 minutes"
    for minutes in (7, 5, 3, 1):
        setup.refused(minutes * MINUTE)

    await setup.run()
    assert setup.chat.said == []
    setup.refused(timedelta(minutes=9, seconds=59))  # one second younger: five count
    await setup.run()

    assert len(setup.chat.said) == 1


# ---- criterion 3: other kinds never count ----------


@pytest.mark.parametrize("kind", ["rate_limited", "csrf_refused", "mail_failed", "code_request_refused"])
async def test_given_50_events_of_another_kind_when_the_agent_runs_then_there_is_no_notice(kind: str) -> None:
    setup = Setup()
    for _ in range(50):
        setup.events.add(setup.clock.now() - MINUTE, kind, 50)

    await setup.run()

    assert setup.chat.said == []


async def test_given_4_wrong_codes_and_many_other_events_when_the_agent_runs_then_there_is_no_notice() -> None:
    setup = Setup()
    setup.refused(MINUTE, count=4)
    for kind in ("rate_limited", "csrf_refused", "mail_failed"):
        setup.events.add(setup.clock.now() - MINUTE, kind, 50)

    await setup.run()

    assert setup.chat.said == []


# ---- criterion 4: at most one notice in 10 minutes ----------


async def test_given_a_notice_when_the_agent_runs_again_then_no_second_one_until_10_minutes_have_passed() -> None:
    setup = Setup()
    setup.refused(MINUTE, count=5)
    await setup.run()

    setup.clock.advance(timedelta(minutes=9, seconds=59))
    setup.refused(timedelta(0), count=7)  # more events, still inside the 10 minutes since the notice
    await setup.run()
    assert len(setup.chat.said) == 1

    setup.clock.advance(timedelta(seconds=1))  # 10 minutes after the notice; the first events are older by now
    await setup.run()
    assert len(setup.chat.said) == 2
    assert "7 wrong" in setup.chat.said[1]


async def test_given_a_failed_send_when_the_agent_runs_again_then_the_notice_is_tried_again() -> None:
    setup = Setup()
    setup.refused(MINUTE, count=5)
    setup.chat.fail_next = True

    with pytest.raises(RuntimeError):
        await setup.run()
    await setup.run()

    assert len(setup.chat.said) == 1


# ---- criterion 6: nothing identifying in the notice or the logs ----------


async def test_given_a_notice_and_a_failure_when_captured_then_no_digest_username_or_code_appears(
    caplog: pytest.LogCaptureFixture,
) -> None:
    setup = Setup()
    setup.refused(MINUTE, count=5)
    caplog.set_level(logging.DEBUG)
    setup.chat.fail_next = True

    with pytest.raises(RuntimeError):
        await setup.run()
    await setup.run()

    seen = caplog.text + " ".join(setup.chat.said)
    for canary in ("CANARYUSER", "CANARYDIGEST", "123456"):
        assert canary not in seen
    assert not caplog.records


@pytest.mark.parametrize("module", ["usecases/code_alert.py", "db/pg_security_events.py"])
def test_given_the_alert_modules_when_parsed_then_none_logs_or_reads_the_clock(module: str) -> None:
    tree = ast.parse((APP / module).read_text(encoding="utf-8"))

    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    imported = {
        (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }

    assert not called & {"now", "utcnow", "time", "getLogger"}
    assert "logging" not in imported
