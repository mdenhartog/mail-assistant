"""Single-use nonces for Telegram buttons that undo or stop a change (spec D17, AC-48; ADR-0046 item 7, ADR-0033).

Each button carries a random nonce. Only its SHA-256 is stored (table ``categories.telegram_action``) with the chat id,
the kind, the target (the list version or plan it belongs to) and an expiry, so a database reader cannot press a
button. A press is a compare-and-set in one statement: the row must match the hash, the chat and the kind, be unused and
unexpired; the first press wins and any other changes nothing. A refused press is classified afterwards only to say why
("Expired", "Already done" or another chat); the classification never changes a row. The clock and the random nonce are
injected and nothing here logs.
"""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

ACTION_TTL: Final = timedelta(hours=24)  # as the Undo of a web change (NOTICE_TTL)


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """One row of ``telegram_action``."""

    nonce_hash: str
    chat_id: int
    kind: str
    target: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Redeemed:
    """The press was the first valid one; ``target`` is what the button belongs to."""

    target: str


class Refusal(enum.Enum):
    """Why a press changed nothing."""

    DONE = "done"  # used already, never made, or made for another kind of button
    EXPIRED = "expired"
    OTHER_CHAT = "other_chat"


class ActionStore(Protocol):
    """``telegram_action`` for one mailbox."""

    async def insert(self, record: ActionRecord) -> None:
        """Store a new record."""
        ...

    async def find(self, nonce_hash: str) -> ActionRecord | None:
        """The record with this hash, used or not."""
        ...

    async def consume(self, nonce_hash: str, chat_id: int, kind: str, now: datetime) -> str | None:
        """Mark it used if it matches, is unused and unexpired; return its target, or ``None`` (one statement)."""
        ...


def digest(nonce: str) -> str:
    """The stored form of a nonce."""
    return hashlib.sha256(nonce.encode()).hexdigest()


class TelegramActions:
    """Issues and redeems button nonces."""

    def __init__(self, store: ActionStore, new_nonce: Callable[[], str]) -> None:
        """Wire the store and the source of random nonces."""
        self._store = store
        self._new_nonce = new_nonce

    async def issue(self, kind: str, target: str, chat_id: int, now: datetime) -> str:
        """Make a nonce for a button, store its hash and return the nonce (the only place it exists)."""
        nonce = self._new_nonce()
        await self._store.insert(ActionRecord(digest(nonce), chat_id, kind, target, now + ACTION_TTL))
        return nonce

    async def redeem(self, nonce: str, kind: str, chat_id: int, now: datetime) -> Redeemed | Refusal:
        """Use the nonce once; say why when it cannot be used."""
        hashed = digest(nonce)
        target = await self._store.consume(hashed, chat_id, kind, now)
        if target is not None:
            return Redeemed(target)
        record = await self._store.find(hashed)
        if record is None or record.kind != kind:
            return Refusal.DONE
        if record.chat_id != chat_id:
            return Refusal.OTHER_CHAT
        return Refusal.EXPIRED if record.used_at is None and record.expires_at <= now else Refusal.DONE
