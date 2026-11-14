"""Test doubles for the wrong-code alert: in-memory security events and a chat that keeps what it says."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class FakeEvents:
    """Security events; the sum follows ``PgSecurityEvents``: newer than ``since`` and with an id above ``after_id``."""

    def __init__(self) -> None:
        self.rows: list[tuple[int, datetime, str, int]] = []  # (id, time, kind, count); ids only go up

    def add(self, at: datetime, kind: str = "code_refused", count: int = 1) -> int:
        row_id = len(self.rows) + 1
        self.rows.append((row_id, at, kind, count))
        return row_id

    async def refused_codes(self, since: datetime, after_id: int) -> int:
        return sum(
            count
            for row_id, at, kind, count in self.rows
            if kind == "code_refused" and at > since and row_id > after_id
        )

    async def newest_id(self) -> int:
        return max((row_id for row_id, *_ in self.rows), default=0)


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
