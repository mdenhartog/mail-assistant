"""The settings store in PostgreSQL: one schedule row, replaced as a whole under a version check (ADR-0025)."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from schedule_policy.policy import TimePolicy, validate
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Schedule
from app.db.repos import PolicyRefused, StoredSettings, VersionConflict

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


def _values(policy: TimePolicy, expected_version: int, via: str, by: str) -> dict[str, object]:
    return {
        "zone": policy.zone,
        "quiet_start": _minutes(policy.quiet_start),
        "quiet_end": _minutes(policy.quiet_end),
        "overview_at": _minutes(policy.overview_at),
        "remind_at": _minutes(policy.remind_at),
        "version": expected_version + 1,
        "updated_via": via,
        "updated_by": by,
    }


async def _replace(session: AsyncSession, values: dict[str, object], expected_version: int) -> Schedule | None:
    """One statement: the first INSERT when nothing is stored, else an UPDATE that only matches the expected version."""
    if expected_version == 0:
        statement = (
            insert(Schedule).values(id=ROW, **values).on_conflict_do_nothing(index_elements=["id"]).returning(Schedule)
        )
    else:
        statement = (
            update(Schedule)
            .where(Schedule.id == ROW, Schedule.version == expected_version)
            .values(updated_at=func.now(), **values)
            .returning(Schedule)
        )
    return (await session.execute(statement)).scalar_one_or_none()


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
        """Replace the whole row if it is still at ``expected_version`` (0 = insert the first row).

        Raises:
            PolicyRefused: the policy breaks a rule; the database was not touched.
            VersionConflict: the row is not at ``expected_version``; nothing was written.
        """
        if problems := validate(policy):
            raise PolicyRefused(problems)
        async with self._sessions.begin() as session:
            row = await _replace(session, _values(policy, expected_version, via, by), expected_version)
        if row is None:
            raise VersionConflict
        return _stored(row)
