"""U-web-settings-26 (AC-13, W-11, ADR-0033): one Telegram notice per web change, at least once, never held."""

from __future__ import annotations

import ast
import logging
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pytest

from app.usecases.web_notice import WebChange, WebNotice
from schedule_policy.policy import TimePolicy
from schedule_policy.testing import FakeClock
from tests.usecases.fakes_dialogue import FakeConversations
from tests.usecases.fakes_web_notice import AT, FakeNoticeStore, RecordingChat, Tokens, change, policy

APP = Path(__file__).resolve().parents[2] / "app"
NOTICE_MODULES = ("usecases/web_notice.py", "db/pg_web_notice.py")


def _notice(store: FakeNoticeStore, chat: RecordingChat, tokens: Tokens | None = None) -> WebNotice:
    return WebNotice(store, chat, tokens or Tokens())


async def test_given_a_web_change_to_version_3_when_the_agent_runs_then_one_notice_with_everything(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store, chat = FakeNoticeStore([change(3)], cursor=2), RecordingChat()

    await _notice(store, chat).run(AT + timedelta(minutes=2))

    assert len(chat.sent) == 1
    text = chat.sent[0].text
    for fact in ("change 3", "Channel: web", "2026-11-11 14:05", "22:00 to 07:00", "was 23:00 to 07:00"):
        assert fact in text
    assert [b.label for b in chat.sent[0].buttons] == ["Undo", "Undo and lock web sign-in"]
    assert not caplog.records


async def test_given_the_notice_was_sent_when_the_agent_runs_again_then_there_is_no_second_notice() -> None:
    store, chat = FakeNoticeStore([change(3)], cursor=2), RecordingChat()
    notice = _notice(store, chat)

    await notice.run(AT)
    await notice.run(AT)

    assert len(chat.sent) == 1
    assert store.cursor == 3


async def test_given_no_web_change_when_the_agent_runs_then_nothing_is_sent() -> None:
    store, chat = FakeNoticeStore([]), RecordingChat()

    await _notice(store, chat).run(AT)

    assert chat.sent == []
    assert store.tokens == []


async def test_given_versions_9_10_and_11_when_the_agent_runs_then_three_notices_in_numeric_order() -> None:
    store = FakeNoticeStore([change(10), change(11), change(9)], cursor=8)
    chat = RecordingChat()

    await _notice(store, chat).run(AT)

    numbers = [text.split("(change ")[1].split(")")[0] for text in (m.text for m in chat.sent)]
    assert numbers == ["9", "10", "11"]
    assert store.cursor == 11


async def test_given_a_burst_when_the_agent_runs_then_each_token_restores_the_values_before_the_first_change() -> None:
    first = change(3, old_start=23, new_start=22)
    store = FakeNoticeStore([first, change(4, old_start=22, new_start=21)], cursor=2)

    await _notice(store, RecordingChat()).run(AT)

    assert [t.version for t in store.tokens] == [3, 4]
    assert {t.before["quiet_start"] for t in store.tokens} == {23 * 60}
    assert all(t.expires_at - t.created_at == timedelta(hours=24) and t.created_at == AT for t in store.tokens)


async def test_given_a_failure_between_the_send_and_the_cursor_when_run_twice_then_sent_twice_and_cursor_advanced() -> (
    None
):
    store, chat = FakeNoticeStore([change(3)], cursor=2), RecordingChat()
    store.fail_on = {"advance"}
    notice = _notice(store, chat)

    with pytest.raises(RuntimeError):
        await notice.run(AT)
    assert store.cursor == 2
    await notice.run(AT)

    assert len(chat.sent) == 2
    assert chat.sent[0].text == chat.sent[1].text  # the same change number
    assert store.cursor == 3
    assert len(store.tokens) == 2
    assert chat.sent[0].buttons != chat.sent[1].buttons  # each send has its own token


async def test_given_the_chat_fails_before_the_send_when_run_again_then_the_cursor_did_not_move_and_it_is_sent() -> (
    None
):
    store, chat = FakeNoticeStore([change(3)], cursor=2), RecordingChat()
    chat.fail_next = True
    notice = _notice(store, chat)

    with pytest.raises(RuntimeError):
        await notice.run(AT)
    assert store.cursor == 2
    await notice.run(AT)

    assert len(chat.sent) == 1
    assert store.cursor == 3


async def test_given_a_failing_token_record_when_the_agent_runs_then_nothing_is_sent_and_the_cursor_stays() -> None:
    store, chat = FakeNoticeStore([change(3)], cursor=2), RecordingChat()
    store.fail_on = {"record_token"}

    with pytest.raises(RuntimeError):
        await _notice(store, chat).run(AT)

    assert chat.sent == []
    assert store.cursor == 2


async def test_given_a_failure_on_the_second_of_two_changes_when_the_agent_runs_then_the_first_is_kept() -> None:
    store, chat = FakeNoticeStore([change(3), change(4)], cursor=2), RecordingChat()
    chat.fail_on_text = "change 4"
    notice = _notice(store, chat)

    with pytest.raises(RuntimeError):
        await notice.run(AT)
    assert store.cursor == 3
    await notice.run(AT)

    assert [m.text.split("(change ")[1][0] for m in chat.sent] == ["3", "4"]


async def test_given_a_pending_telegram_dialogue_when_a_notice_is_sent_then_the_conversation_row_is_unchanged() -> None:
    clock = FakeClock(AT)
    conversations = FakeConversations(clock)
    started = await conversations.start("settings", None, "card", {"key": "quiet"}, timedelta(minutes=15))
    store, chat = FakeNoticeStore([change(3)], cursor=2), RecordingChat()

    await _notice(store, chat).run(clock.now())

    assert await conversations.current() == started
    assert conversations.starts == 1
    assert len(chat.sent) == 1


async def test_given_quiet_hours_the_change_itself_set_when_the_agent_runs_inside_them_then_the_notice_is_sent() -> (
    None
):
    quiet = TimePolicy("Europe/Amsterdam", time(13, 0), time(17, 0), time(18, 0), time(9, 0))  # 13:00 to 17:00
    clock = FakeClock(datetime(2026, 11, 11, 13, 30, tzinfo=UTC))  # 14:30 in Amsterdam
    assert quiet.is_quiet(time(14, 30))
    store, chat = FakeNoticeStore([WebChange(3, AT, policy(), quiet)], cursor=2), RecordingChat()

    await _notice(store, chat).run(clock.now())

    assert len(chat.sent) == 1


def _called(tree: ast.AST) -> set[str]:
    """Dotted names of what the module calls: ``datetime.now``, ``secrets.token_urlsafe``, ``uuid4``."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            parts, func = [], node.func
            while isinstance(func, ast.Attribute):
                parts.append(func.attr)
                func = func.value
            if isinstance(func, ast.Name):
                names.add(".".join([func.id, *reversed(parts)]))
    return names


@pytest.mark.parametrize("module", NOTICE_MODULES)
def test_given_the_notice_modules_when_parsed_then_none_reads_the_clock_or_makes_random_values(module: str) -> None:
    tree = ast.parse((APP / module).read_text(encoding="utf-8"))
    imported = {
        (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }

    called = _called(tree)

    assert not {name for name in called if name in {"datetime.now", "time.time", "uuid4", "uuid.uuid4", "urandom"}}
    assert not {name for name in called if name.split(".")[0] in {"random", "secrets"}}
    assert not {name.split(".")[0] for name in imported} & {"random", "secrets", "uuid"}


async def test_given_a_failure_with_a_canary_zone_and_token_when_the_agent_runs_then_no_log_line_holds_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store, chat = FakeNoticeStore([change(3)], cursor=2), RecordingChat()
    store.fail_on = {"advance"}
    caplog.set_level(logging.DEBUG)

    with pytest.raises(RuntimeError):
        await _notice(store, chat).run(AT)

    assert "Canary" not in caplog.text
    assert "CANARYTOKEN" not in caplog.text
    assert "T0000" not in caplog.text
