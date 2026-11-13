"""Test doubles for the wrong-code alert: in-memory security events and a chat that keeps what it says."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class FakeEvents:
    """Security events as (time, kind, count); the sum follows ``PgSecurityEvents``."""

    def __init__(self) -> None:
        self.rows: list[tuple[datetime, str, int]] = []

    def add(self, at: datetime, kind: str = "code_refused", count: int = 1) -> None:
        self.rows.append((at, kind, count))

    async def refused_codes(self, since: datetime) -> int:
        return sum(count for at, kind, count in self.rows if kind == "code_refused" and at > since)


class SpyChat:
    """Keeps every plain note; ``fail_next`` makes one ``say`` raise."""

    def __init__(self) -> None:
        self.said: list[str] = []
        self.fail_next = False

    async def say(self, text: str) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("telegram is down for username CANARYUSER digest CANARYDIGEST code 123456")
        self.said.append(text)
