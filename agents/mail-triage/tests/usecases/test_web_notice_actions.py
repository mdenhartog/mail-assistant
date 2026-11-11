"""U-web-settings-27 (AC-13, AC-27, W-11, ADR-0033): Undo, Undo and lock, and /web_unlock from a web notice."""

from __future__ import annotations

import ast
import itertools
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from app.adapters.telegram_inbox import Command
from app.core import settings_text
from app.usecases.dispatch import CommandRouter
from app.usecases.web_notice import NoticeToken, WebChange, WebNotice
from app.usecases.web_notice_actions import WebNoticeActions
from tests.usecases.fakes_web_actions import FakeLock, FakeSettingsWriter, FakeTokens
from tests.usecases.fakes_web_notice import AT, FakeNoticeStore, RecordingChat, Tokens, change, policy
from tests.usecases.test_dispatch import Rig

APP = Path(__file__).resolve().parents[2] / "app"
ACTION_MODULES = ("usecases/web_notice_actions.py", "db/pg_web_lock.py")
CHAT, STRANGER, OWNER = 1, 2, "42"
_UPDATES = itertools.count(1000)


def tap(data: str, chat_id: int = CHAT) -> Command:
    return Command("button", data, chat_id, 9, "cb1", next(_UPDATES))


def say(data: str, chat_id: int = CHAT) -> Command:
    return Command("text", data, chat_id, 10, None, next(_UPDATES))


class Setup:
    """A router with the web actions registered, over in-memory token records, lock and settings row."""

    def __init__(self, rig: Rig, records: list[NoticeToken], row: FakeSettingsWriter, lock: FakeLock) -> None:
        self.rig, self.records, self.row, self.lock = rig, records, row, lock
        self.tokens = FakeTokens(records)
        self.actions = WebNoticeActions(self.tokens, lock, row, rig.chat, chat_id=CHAT, by=OWNER, now=rig.clock.now)
        self.router: CommandRouter = rig.router()
        self.router.register_web_actions(self.actions)

    def token(self, version: int) -> str:
        return next(r.token for r in self.records if r.version == version)


async def burst(
    versions: tuple[int, ...] = (3, 4, 5), *, row_version: int | None = None, first_row: bool = False
) -> Setup:
    """Web changes ``versions`` announced in one run; the row ends at ``row_version`` (default: the last one)."""
    rig = Rig()
    rig.clock.set(AT)
    top = max(versions)
    steps = [change(v, old_start=23 - i, new_start=22 - i) for i, v in enumerate(versions)]
    if first_row:  # the first saved row replaced nothing
        steps[0] = WebChange(steps[0].version, AT, None, steps[0].new)
    store = FakeNoticeStore(steps, cursor=min(versions) - 1)
    await WebNotice(store, RecordingChat(), Tokens()).run(rig.clock.now())
    row = FakeSettingsWriter(policy(22 - len(versions) + 1), row_version or top)
    return Setup(rig, store.tokens, row, FakeLock())


# ---- criteria 1 to 3: Undo goes back to before the burst, guarded by the version ------------------------------------


async def test_given_changes_3_4_5_when_undo_of_notice_5_is_tapped_then_the_values_from_before_change_3_are_back() -> None:
    setup = await burst()

    await setup.router.handle(tap(f"webundo:{setup.token(5)}"))

    assert setup.row.policy == policy(23)
    assert setup.row.audit == [(6, "telegram", OWNER)]  # one audit record for the whole burst
    assert setup.rig.chat.edited == [(9, settings_text.WEB_UNDONE)]
    assert setup.rig.chat.acknowledged == ["cb1"]
    assert setup.lock.locked_at is None


async def test_given_changes_3_4_5_when_undo_of_notice_3_is_tapped_then_the_result_is_the_same() -> None:
    setup = await burst()

    await setup.router.handle(tap(f"webundo:{setup.token(3)}"))

    assert setup.row.policy == policy(23)
    assert len(setup.row.audit) == 1


async def test_given_telegram_changed_the_row_after_the_burst_when_undo_is_tapped_then_nothing_changes() -> None:
    setup = await burst(row_version=6)
    before = setup.row.policy

    await setup.router.handle(tap(f"webundo:{setup.token(5)}"))

    assert setup.row.policy == before
    assert setup.row.audit == []
    assert setup.rig.chat.edited == [(9, settings_text.UNDO_CHANGED)]


async def test_given_a_later_burst_when_undo_of_an_older_notice_is_tapped_then_it_is_refused_and_nothing_changes() -> None:
    setup = await burst((3, 4))
    later = FakeNoticeStore([change(5, old_start=21, new_start=20)], cursor=4)
    await WebNotice(later, RecordingChat(), Tokens()).run(setup.rig.clock.now())
    setup.records.append(
        NoticeToken("L" * 22, 5, later.tokens[0].before, AT, AT + timedelta(hours=24)),
    )
    setup.row.version = 5

    await setup.router.handle(tap(f"webundo:{setup.token(3)}"))

    assert setup.row.audit == []  # the older notice does not silently undo the later change too
    assert setup.rig.chat.edited == [(9, settings_text.UNDO_CHANGED)]


async def test_given_the_first_saved_row_when_undo_is_tapped_then_it_says_there_is_nothing_to_undo() -> None:
    setup = await burst((1,), first_row=True)

    await setup.router.handle(tap(f"webundo:{setup.token(1)}"))

    assert setup.row.audit == []
    assert setup.rig.chat.edited == [(9, settings_text.NOTHING_TO_UNDO)]


async def test_given_a_before_that_is_no_longer_allowed_when_undo_is_tapped_then_nothing_is_written() -> None:
    setup = await burst()
    setup.records[:] = [
        NoticeToken(r.token, r.version, {**r.before, "zone": "Not/AZone"}, r.created_at, r.expires_at)
        for r in setup.records
    ]

    await setup.router.handle(tap(f"webundo:{setup.token(5)}"))

    assert setup.row.audit == []
    assert setup.rig.chat.edited == [(9, settings_text.UNDO_REFUSED)]


# ---- criteria 4 and 5: Undo and lock ---------------------------------------------------------------------------------


async def test_given_undo_and_lock_when_tapped_then_the_lock_is_set_and_the_values_are_back() -> None:
    setup = await burst()

    await setup.router.handle(tap(f"weblock:{setup.token(5)}"))

    assert setup.lock.locked_at == AT
    assert setup.row.policy == policy(23)
    assert setup.rig.chat.edited == [(9, settings_text.web_locked(settings_text.WEB_UNDONE))]
    assert "/web_unlock" in setup.rig.chat.edited[0][1]


async def test_given_undo_and_lock_when_the_undo_conflicts_then_the_lock_is_set_anyway() -> None:
    setup = await burst(row_version=6)

    await setup.router.handle(tap(f"weblock:{setup.token(5)}"))

    assert setup.lock.locked_at == AT
    assert setup.row.audit == []
    assert setup.rig.chat.edited == [(9, settings_text.web_locked(settings_text.UNDO_CHANGED))]


async def test_given_undo_and_lock_tapped_twice_when_handled_then_one_lock_and_one_undo() -> None:
    setup = await burst()
    data = f"weblock:{setup.token(5)}"

    await setup.router.handle(tap(data))
    await setup.router.handle(tap(data))

    assert setup.lock.sets == 1
    assert len(setup.row.audit) == 1
    assert setup.rig.chat.edited[1] == (9, settings_text.WEB_DONE)


async def test_given_undo_and_lock_on_two_notices_when_both_are_tapped_then_the_lock_stays_one_and_set() -> None:
    setup = await burst()

    await setup.router.handle(tap(f"webundo:{setup.token(5)}"))
    await setup.router.handle(tap(f"weblock:{setup.token(4)}"))

    assert setup.lock.sets == 1  # the lock stays available after an Undo: the version guard stops a second undo
    assert len(setup.row.audit) == 1


async def test_given_the_lock_cannot_be_written_when_undo_and_lock_is_tapped_then_nothing_is_undone() -> None:
    setup = await burst()
    setup.lock.fail = True

    with pytest.raises(RuntimeError):
        await setup.router.handle(tap(f"weblock:{setup.token(5)}"))

    assert setup.row.audit == []  # the lock is written first
    assert setup.rig.chat.edited == []
    assert setup.tokens.records  # the token is kept, so the tap can be handled again


# ---- criterion 6: /web_unlock ---------------------------------------------------------------------------------------


async def test_given_a_locked_web_sign_in_when_the_owner_sends_web_unlock_then_it_is_cleared_and_said() -> None:
    setup = await burst()
    await setup.router.handle(tap(f"weblock:{setup.token(5)}"))

    await setup.router.handle(say("/web_unlock"))

    assert setup.lock.locked_at is None
    assert setup.rig.chat.said == [settings_text.WEB_UNLOCKED]


async def test_given_the_bot_name_and_extra_words_when_web_unlock_is_sent_then_it_is_still_the_command() -> None:
    setup = await burst()
    setup.lock.locked_at = AT

    await setup.router.handle(say("/web_unlock@MailBot now"))

    assert setup.lock.locked_at is None


async def test_given_no_lock_when_web_unlock_is_sent_then_it_says_there_was_none() -> None:
    setup = await burst()

    await setup.router.handle(say("/web_unlock"))

    assert setup.rig.chat.said == [settings_text.WEB_NOT_LOCKED]


async def test_given_another_chat_when_web_unlock_is_sent_then_nothing_happens_and_nothing_is_answered() -> None:
    setup = await burst()
    setup.lock.locked_at = AT

    await setup.router.handle(say("/web_unlock", STRANGER))

    assert setup.lock.locked_at == AT
    assert setup.rig.chat.said == []
    assert setup.rig.chat.edited == []


# ---- criterion 7: an expired or used token ---------------------------------------------------------------------------


async def test_given_an_expired_token_when_tapped_then_the_message_says_expired_and_nothing_is_written() -> None:
    setup = await burst()
    setup.rig.clock.set(AT + timedelta(hours=24))  # the token life ends at this instant

    await setup.router.handle(tap(f"weblock:{setup.token(5)}"))

    assert setup.rig.chat.edited == [(9, "Expired")]
    assert setup.row.audit == []
    assert setup.lock.locked_at is None


async def test_given_a_token_just_before_it_expires_when_tapped_then_it_works() -> None:
    setup = await burst()
    setup.rig.clock.set(AT + timedelta(hours=24) - timedelta(seconds=1))

    await setup.router.handle(tap(f"webundo:{setup.token(5)}"))

    assert len(setup.row.audit) == 1


async def test_given_a_used_token_when_tapped_again_then_the_message_says_already_done() -> None:
    setup = await burst()
    data = f"webundo:{setup.token(5)}"
    await setup.router.handle(tap(data))
    setup.row.audit.clear()

    await setup.router.handle(tap(data))

    assert setup.rig.chat.edited[-1] == (9, "Already done")
    assert setup.row.audit == []


async def test_given_an_unknown_token_when_tapped_then_the_message_says_already_done_and_nothing_is_written() -> None:
    setup = await burst()

    await setup.router.handle(tap(f"weblock:{'Z' * 22}"))

    assert setup.rig.chat.edited == [(9, "Already done")]
    assert setup.lock.locked_at is None


@pytest.mark.parametrize("data", ["webundo:short", f"weblock:{'a' * 41}", f"webundo:{'a' * 21}!", "webundo:", "webundo"])
async def test_given_a_malformed_web_button_when_tapped_then_it_is_ignored(data: str) -> None:
    setup = await burst()

    await setup.router.handle(tap(data))

    assert setup.rig.chat.edited == []
    assert setup.rig.chat.said == []
    assert setup.row.audit == []


# ---- criterion 8: only the allowed chat ------------------------------------------------------------------------------


async def test_given_a_tap_from_another_chat_with_a_valid_token_when_handled_then_it_is_ignored() -> None:
    setup = await burst()

    await setup.router.handle(tap(f"weblock:{setup.token(5)}", STRANGER))

    assert setup.lock.locked_at is None
    assert setup.row.audit == []
    assert setup.rig.chat.edited == []
    assert setup.rig.chat.said == []
    assert setup.tokens.records  # the token is untouched


# ---- criterion 9 (agent level): a pending Telegram dialogue is never replaced ---------------------------------------------


async def test_given_a_pending_telegram_dialogue_when_web_buttons_and_unlock_are_used_then_the_dialogue_is_unchanged() -> None:
    setup = await burst()
    started = await setup.rig.conversations.start("settings", None, "card", {"k": "v"}, timedelta(minutes=15))
    starts = setup.rig.conversations.starts

    await setup.router.handle(tap(f"webundo:{setup.token(5)}"))
    await setup.router.handle(tap(f"weblock:{setup.token(4)}"))
    await setup.router.handle(say("/web_unlock"))

    assert await setup.rig.conversations.current() == started
    assert setup.rig.conversations.starts == starts
    assert setup.rig.chat.offered == []


# ---- criterion 10: no canary in the logs, and no clock or random value -------------------------------------------------


async def test_given_a_failure_with_a_canary_zone_and_token_when_a_button_is_tapped_then_no_log_line_holds_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    setup = await burst()
    setup.lock.fail = True  # the error text holds "Canary/Zone" and "CANARYTOKEN"
    caplog.set_level(logging.DEBUG)

    with pytest.raises(RuntimeError):
        await setup.router.handle(tap(f"weblock:{setup.token(5)}"))
    await setup.router.handle(tap(f"webundo:{'Z' * 22}"))  # an unknown token

    for secret in ("Canary", "CANARYTOKEN", setup.token(5), "Z" * 22, "Europe/Amsterdam"):
        assert secret not in caplog.text


def _called(tree: ast.AST) -> set[str]:
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


@pytest.mark.parametrize("module", ACTION_MODULES)
def test_given_the_action_modules_when_parsed_then_none_reads_the_clock_or_makes_random_values(module: str) -> None:
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
