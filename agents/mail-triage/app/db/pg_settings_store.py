"""The settings store in PostgreSQL: one schedule row, replaced as a whole under a version check (ADR-0025)."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from schedule_policy.policy import TimePolicy
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Schedule
from app.db.repos import StoredSettings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROW = 1


def _minutes(clock: time) -> int:
    return clock.hour * 60 + clock.minute


def _clock(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _stored(row: Schedule) -> StoredSettings:
    policy = TimePolicy(
        zone=row.zone,
        quiet_start=_clock(row.quiet_start),
        quiet_end=_clock(row.quiet_end),
        overview_at=_clock(row.overview_at),
        remind_at=_clock(row.remind_at),
    )
    return StoredSettings(policy, row.version, row.updated_at, row.updated_via, row.updated_by)


class PgSettingsStore:
    """Satisfies ``SettingsStore``; every method is one short transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def read(self) -> StoredSettings | None:
        """The stored row, or None when none was ever written."""
        async with self._sessions() as session:
            row = await session.get(Schedule, ROW)
        return _stored(row) if row else None

    async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
        """Insert the first row (``expected_version`` 0)."""
        values = {
            "id": ROW,
            "zone": policy.zone,
            "quiet_start": _minutes(policy.quiet_start),
            "quiet_end": _minutes(policy.quiet_end),
            "overview_at": _minutes(policy.overview_at),
            "remind_at": _minutes(policy.remind_at),
            "version": expected_version + 1,
            "updated_via": via,
            "updated_by": by,
        }
        async with self._sessions.begin() as session:
            row = (await session.execute(insert(Schedule).values(values).returning(Schedule))).scalar_one()
        return _stored(row)
