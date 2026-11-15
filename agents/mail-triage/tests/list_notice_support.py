"""Test doubles for the list notice: nonce store, list store with the database's derived audit, chat and lock."""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.adapters.telegram_inbox import Command
from app.core import list_text
from app.core.list_text import ListCategory
from app.usecases.list_notice import ListChange, ListChanged, ListNotice, ListNoticeActions
from app.usecases.telegram_actions import ActionRecord, TelegramActions
from tests.fakes.fake_telegram import FakeTelegram

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.alert_text import AlertMessage

AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
LATER = AT + timedelta(minutes=5)
CHAT = 4242
AGENT_DIGEST = hashlib.sha256(b"mail_triage_runtime").hexdigest()
WEB_DIGEST = hashlib.sha256(b"web_settings_runtime").hexdigest()


def cats(*names: str) -> tuple[ListCategory, ...]:
    """A list of categories with an id per name."""
    return tuple(ListCategory(f"id-{name}", name, f"about {name}") for name in names)


class Nonces:
    """A nonce source that is valid for button data and different every time."""

    def __init__(self) -> None:
        self._count = itertools.count(1)

    def __call__(self) -> str:
        return f"n{next(self._count):021d}"


class FakeActionStore:
    """``telegram_action`` with the compare-and-set of the real table."""

    def __init__(self) -> None:
        self.rows: dict[str, ActionRecord] = {}

    async def insert(self, record: ActionRecord) -> None:
        self.rows[record.nonce_hash] = record

    async def find(self, nonce_hash: str) -> ActionRecord | None:
        return self.rows.get(nonce_hash)

    async def consume(self, nonce_hash: str, chat_id: int, kind: str, now: datetime) -> str | None:
        row = self.rows.get(nonce_hash)
        if (
            row is None
            or row.used_at is not None
            or row.chat_id != chat_id
            or row.kind != kind
            or row.expires_at <= now
        ):
            return None
        self.rows[nonce_hash] = ActionRecord(
            row.nonce_hash, row.chat_id, row.kind, row.target, row.expires_at, used_at=now
        )
        return row.target


@dataclass(frozen=True, slots=True)
class AuditRow:
    """What the database keeps for one list version."""

    version: int
    channel: str
    actor_digest: str
    old: tuple[ListCategory, ...]
    new: tuple[ListCategory, ...]
    at: datetime


@dataclass
class FakeListStore:
    """The list, its audit and the cursor; channel and actor are derived here as the trigger does."""

    audit: list[AuditRow] = field(default_factory=list)
    cursor: int = 0

    def save(self, new: tuple[ListCategory, ...], *, channel: str = "web") -> None:
        """A list change by another login than the agent's."""
        self._append(new, channel, AGENT_DIGEST if channel == "telegram" else WEB_DIGEST)

    def _append(self, new: tuple[ListCategory, ...], channel: str, digest: str) -> None:
        old = self.audit[-1].new if self.audit else ()
        self.audit.append(AuditRow(len(self.audit) + 1, channel, digest, old, new, AT))

    @property
    def latest(self) -> int:
        return self.audit[-1].version if self.audit else 0

    async def last_announced(self) -> int:
        return self.cursor

    async def pending_after(self, version: int) -> list[ListChange]:
        return [ListChange(r.version, r.at, r.channel, r.old, r.new) for r in self.audit if r.version > version]

    async def change(self, version: int) -> ListChange | None:
        row = next((r for r in self.audit if r.version == version), None)
        return None if row is None else ListChange(row.version, row.at, row.channel, row.old, row.new)

    async def advance(self, version: int) -> None:
        self.cursor = max(self.cursor, version)

    async def restore(self, categories: Sequence[ListCategory], expected_version: int) -> int:
        if self.latest != expected_version:
            raise ListChanged
        self._append(tuple(categories), "telegram", AGENT_DIGEST)
        return self.latest


class RecordingChat(FakeTelegram):
    """The canary-checking Telegram double, keeping what was sent, edited and said."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[AlertMessage] = []
        self.edits: list[tuple[int, str]] = []
        self.notes: list[str] = []
        self.fail_send = False

    async def send(self, message: AlertMessage) -> int:
        if self.fail_send:
            raise RuntimeError("send broke")
        self.sent.append(message)
        return await super().send(message)

    async def edit_message(self, message_id: int, text: str) -> None:
        self.edits.append((message_id, text))
        await super().edit_message(message_id, text)

    async def say(self, text: str) -> None:
        self.notes.append(text)
        await super().say(text)


class FakeLock:
    """``web_auth.web_lock``."""

    def __init__(self) -> None:
        self.locked = False

    async def lock(self, now: datetime) -> bool:
        newly = not self.locked
        self.locked = True
        return newly


class Rig:
    """A notice and its button handler on shared fakes."""

    def __init__(self) -> None:
        self.clock = [LATER]
        self.store, self.chat, self.lock = FakeListStore(), RecordingChat(), FakeLock()
        actions = TelegramActions(FakeActionStore(), Nonces())
        self.notice = ListNotice(self.store, self.chat, actions, chat_id=CHAT)
        self.buttons = ListNoticeActions(
            actions, self.store, self.lock, self.chat, chat_id=CHAT, now=lambda: self.clock[0]
        )

    async def press(self, data: str, *, chat_id: int = CHAT, message_id: int = 7) -> None:
        split = list_text.split_button(data)
        assert split is not None
        await self.buttons.on_button(Command("button", data, chat_id, message_id, "cb", 1), *split)


def seeded() -> Rig:
    rig = Rig()
    rig.store.save(cats("Bills", "Travel"), channel="telegram")  # version 1: the agent's own seed, never announced
    rig.store.cursor = 1
    return rig
