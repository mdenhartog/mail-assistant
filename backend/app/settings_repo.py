"""Read access to ``settings.schedule`` as the web role (U-web-settings-20); the write part is U-web-settings-21."""

from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy import text

from app.db import Database
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy

_SELECT = text(
    "SELECT zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_at, updated_via "
    "FROM settings.schedule WHERE id = 1"
)


@dataclass(frozen=True, slots=True)
class StoredSettings:
    """The schedule row as the page sees it; ``version`` 0 means no row yet (defaults)."""

    policy: TimePolicy
    version: int
    updated_at: datetime | None
    updated_via: str | None


def _clock(minute_of_day: int) -> time:
    return time(minute_of_day // 60, minute_of_day % 60)


class SettingsRepository:
    """Reads the single schedule row; never the actor column."""

    def __init__(self, database: Database) -> None:
        """Keep the database access."""
        self._database = database

    async def read(self) -> StoredSettings:
        """Return the stored settings, or the defaults at version 0 when no row exists.

        Returns:
            The settings; ``updated_at`` and ``updated_via`` are None at version 0.
        """
        async with self._database.session() as session, session.begin():
            row = (await session.execute(_SELECT)).one_or_none()
        if row is None:
            return StoredSettings(DEFAULT_POLICY, 0, None, None)
        policy = TimePolicy(
            zone=row.zone,
            quiet_start=_clock(row.quiet_start),
            quiet_end=_clock(row.quiet_end),
            overview_at=_clock(row.overview_at),
            remind_at=_clock(row.remind_at),
        )
        return StoredSettings(policy, row.version, row.updated_at, row.updated_via)
