"""Read and write access to ``settings.schedule`` as the web role (U-web-settings-20 and U-web-settings-21)."""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from sqlalchemy import Row, text

from app.db import Database
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy

_SELECT = text(
    "SELECT zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_at, updated_via "
    "FROM settings.schedule WHERE id = 1"
)
_INSERT = text(
    "INSERT INTO settings.schedule "
    "(id, zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by) "
    "VALUES (1, :zone, :quiet_start, :quiet_end, :overview_at, :remind_at, 1, 'web', :by) "
    "ON CONFLICT (id) DO NOTHING "
    "RETURNING zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_at, updated_via"
)
_UPDATE = text(
    "UPDATE settings.schedule SET zone = :zone, quiet_start = :quiet_start, quiet_end = :quiet_end, "
    "overview_at = :overview_at, remind_at = :remind_at, version = :version + 1, updated_via = 'web', "
    "updated_by = :by WHERE id = 1 AND version = :version "
    "RETURNING zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_at, updated_via"
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


def _minutes(clock: time) -> int:
    return clock.hour * 60 + clock.minute


def _stored(row: Row[Any]) -> StoredSettings:
    policy = TimePolicy(
        zone=row.zone,
        quiet_start=_clock(row.quiet_start),
        quiet_end=_clock(row.quiet_end),
        overview_at=_clock(row.overview_at),
        remind_at=_clock(row.remind_at),
    )
    return StoredSettings(policy, row.version, row.updated_at, row.updated_via)


class VersionConflict(Exception):  # noqa: N818  # a state of the row, not a fault of the caller
    """The row is not at the version the writer based its change on; carries the row as it is now."""

    def __init__(self, current: StoredSettings) -> None:
        """Keep the current row (the defaults at version 0 when there is none)."""
        super().__init__("settings version conflict")
        self.current = current


class SettingsRepository:
    """Reads and writes the single schedule row; never reads the actor column."""

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
        return _stored(row)

    async def write(self, policy: TimePolicy, expected_version: int, username_hash: str) -> StoredSettings:
        """Store the policy if the row is still at ``expected_version``; one transaction, audited by the database.

        Version 0 inserts the first row, any other version replaces the values with one guarded UPDATE. The guard
        sets the channel and the audit trigger records the change in the same transaction.

        Args:
            policy: The new, already validated values.
            expected_version: The version the change is based on; 0 when no row exists yet.
            username_hash: The 32 hex digest of the signed-in user; stored as ``web:<digest>``.

        Returns:
            The row as stored, at ``expected_version + 1``.

        Raises:
            VersionConflict: The row is at another version (or missing); nothing was written.
            DBAPIError: The database refused the write (check, guard 42501, failing audit); nothing was written.
        """
        params: dict[str, Any] = {
            "zone": policy.zone,
            "quiet_start": _minutes(policy.quiet_start),
            "quiet_end": _minutes(policy.quiet_end),
            "overview_at": _minutes(policy.overview_at),
            "remind_at": _minutes(policy.remind_at),
            "by": f"web:{username_hash}",
        }
        statement = _INSERT if expected_version == 0 else _UPDATE
        if expected_version != 0:
            params["version"] = expected_version
        async with self._database.session() as session, session.begin():
            row = (await session.execute(statement, params)).one_or_none()
            if row is not None:
                return _stored(row)
            current = (await session.execute(_SELECT)).one_or_none()
        raise VersionConflict(StoredSettings(DEFAULT_POLICY, 0, None, None) if current is None else _stored(current))
