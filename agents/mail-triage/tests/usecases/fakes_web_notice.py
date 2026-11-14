"""Test doubles for the web notice: an in-memory notice store, a recording chat and a token source."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

from app.usecases.web_notice import OpenBurst, WebChange
from schedule_policy.policy import TimePolicy

if TYPE_CHECKING:
    from app.core.alert_text import AlertMessage
    from app.usecases.web_notice import NoticeToken

AT = datetime(2026, 11, 11, 13, 5, tzinfo=UTC)
BASE = TimePolicy("Europe/Amsterdam", time(23, 0), time(7, 0), time(18, 0), time(9, 0))


def policy(quiet_start: int = 23) -> TimePolicy:
    """The base policy with another quiet start hour."""
    return TimePolicy("Europe/Amsterdam", time(quiet_start, 0), time(7, 0), time(18, 0), time(9, 0))


def change(version: int, *, old_start: int = 23, new_start: int = 22) -> WebChange:
    """A web change that made ``version``."""
    return WebChange(version, AT, policy(old_start), policy(new_start))


class FakeNoticeStore:
    """Changes by version, the cursor and the token records; ``fail_on`` makes one named call raise once."""

    def __init__(self, changes: list[WebChange] | None = None, cursor: int = 0) -> None:
        self.changes = list(changes or [])
        self.cursor = cursor
        self.tokens: list[NoticeToken] = []
        self.fail_on: set[str] = set()

    def _maybe_fail(self, name: str) -> None:
        if name in self.fail_on:
            self.fail_on.discard(name)
            raise RuntimeError(f"{name} broke for zone Canary/Zone token CANARYTOKEN")

    async def last_announced(self) -> int:
        return self.cursor

    async def pending_after(self, version: int) -> list[WebChange]:
        return sorted((c for c in self.changes if c.version > version), key=lambda c: c.version)

    async def open_burst(self, after: int, now: datetime) -> OpenBurst | None:
        live = sorted((t for t in self.tokens if t.version > after and t.expires_at > now), key=lambda t: t.version)
        return OpenBurst(live[0].burst_id, live[0].first_version, live[0].before) if live else None

    async def record_token(self, token: NoticeToken) -> None:
        self._maybe_fail("record_token")
        self.tokens.append(token)

    async def advance(self, version: int) -> None:
        self._maybe_fail("advance")
        self.cursor = max(self.cursor, version)


class RecordingChat:
    """Keeps every message sent; ``fail_next`` or ``fail_on_text`` makes one send raise."""

    def __init__(self) -> None:
        self.sent: list[AlertMessage] = []
        self.fail_next = False
        self.fail_on_text: str | None = None

    async def send(self, message: AlertMessage) -> int:
        if self.fail_next or (self.fail_on_text is not None and self.fail_on_text in message.text):
            self.fail_next = False
            self.fail_on_text = None
            raise RuntimeError("telegram is down")
        self.sent.append(message)
        return len(self.sent)


class Tokens:
    """A token source that counts: 22-character URL-safe strings."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> str:
        self.count += 1
        return f"T{self.count:021d}"
