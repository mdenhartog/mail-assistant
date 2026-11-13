"""Test doubles for the web notice buttons: token records, the lock row and the settings row, all in memory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repos import PolicyRefused, StoredSettings, VersionConflict
from schedule_policy.policy import validate
from tests.usecases.fakes_web_notice import AT

if TYPE_CHECKING:
    from datetime import datetime

    from app.usecases.web_notice import NoticeToken
    from schedule_policy.policy import TimePolicy


class FakeTokens:
    """The token records; it shares its list with ``FakeNoticeStore.tokens`` so the real notice use case fills it."""

    def __init__(self, records: list[NoticeToken]) -> None:
        self.records = records
        self.fail_on: set[str] = set()

    async def find(self, token: str) -> NoticeToken | None:
        return next((r for r in self.records if r.token == token), None)

    async def burst_end(self, burst_id: str, first_version: int) -> int:
        return max(
            (r.version for r in self.records if r.burst_id == burst_id and r.version >= first_version), default=0
        )

    async def consume(self, token: str) -> bool:
        found = await self.find(token)
        if found is None:
            return False
        self.records.remove(found)
        return True


class FakeLock:
    """The single lock row; ``sets`` counts the calls that really created it, ``calls`` every write, ``fail`` raises."""

    def __init__(self, *, fail: bool = False) -> None:
        self.locked_at: datetime | None = None
        self.sets = 0
        self.calls = 0
        self.fail = fail

    async def is_locked(self) -> bool:
        return self.locked_at is not None

    async def lock(self, now: datetime) -> bool:
        self.calls += 1
        if self.fail:
            raise RuntimeError("lock broke for zone Canary/Zone token CANARYTOKEN")
        if self.locked_at is not None:
            return False
        self.locked_at = now
        self.sets += 1
        return True

    async def unlock(self) -> bool:
        was = self.locked_at is not None
        self.locked_at = None
        return was


class FakeSettingsWriter:
    """The schedule row with a version guard and an audit list: one entry per accepted write."""

    def __init__(self, policy: TimePolicy, version: int) -> None:
        self.policy = policy
        self.version = version
        self.audit: list[tuple[int, str, str]] = []  # (new version, via, by)

    async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
        if problems := validate(policy):
            raise PolicyRefused(problems)
        if expected_version != self.version:
            raise VersionConflict
        self.policy = policy
        self.version += 1
        self.audit.append((self.version, via, by))
        return StoredSettings(policy, self.version, AT, via, by)
