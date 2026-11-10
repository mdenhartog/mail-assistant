"""The settings store in PostgreSQL: one schedule row, replaced as a whole under a version check (ADR-0025)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import Integer, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError

from app.db.models import Schedule, SettingsChange
from app.db.repos import (
    NothingToUndo,
    PolicyRefused,
    SettingsStoreFailure,
    SettingsView,
    StoredSettings,
    StoredSettingsInvalid,
    VersionConflict,
)
from schedule_policy.policy import TimePolicy, validate

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROW = 1
_VALUE_COLUMNS = ("zone", "quiet_start", "quiet_end", "overview_at", "remind_at")


def _minutes(clock: time) -> int:
    return clock.hour * 60 + clock.minute


def _clock(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _policy(columns: Mapping[str, Any]) -> TimePolicy:
    """The policy in a row or in the ``old`` image of an audit record (same column names)."""
    return TimePolicy(
        zone=columns["zone"],
        quiet_start=_clock(columns["quiet_start"]),
        quiet_end=_clock(columns["quiet_end"]),
        overview_at=_clock(columns["overview_at"]),
        remind_at=_clock(columns["remind_at"]),
    )


def _stored(row: Schedule) -> StoredSettings:
    columns = {name: getattr(row, name) for name in _VALUE_COLUMNS}
    return StoredSettings(_policy(columns), row.version, row.updated_at, row.updated_via, row.updated_by)


def _broken_rules(row: Schedule) -> tuple[str, ...]:
    """The rule ids the row breaks (none when usable); a NULL an operator allowed is ``value_missing``."""
    if any(getattr(row, name) is None for name in _VALUE_COLUMNS):
        return ("value_missing",)
    return tuple(problem.rule for problem in validate(_stored(row).policy))


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


async def _replace_or_conflict(
    session: AsyncSession, policy: TimePolicy, expected_version: int, via: str, by: str
) -> StoredSettings:
    """One statement: the first INSERT when nothing is stored, else an UPDATE that only matches the expected version."""
    values = _values(policy, expected_version, via, by)
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
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is None:
        raise VersionConflict
    return _stored(row)


async def _undo_in(session: AsyncSession, expected_version: int, via: str, by: str) -> StoredSettings:
    """The undo inside one transaction: lock the row, check the version, replace with the previous values."""
    current = (await session.execute(select(Schedule).where(Schedule.id == ROW).with_for_update())).scalar_one_or_none()
    if current is None or current.version != expected_version:
        raise VersionConflict
    # The record of the change that made this version: matched by version, not by time, so a transaction that started
    # early and committed late cannot be mistaken for the latest.
    previous = (
        await session.execute(
            select(SettingsChange.old)
            .where(SettingsChange.new["version"].astext.cast(Integer) == expected_version)
            .order_by(SettingsChange.at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if previous is None:
        raise NothingToUndo
    policy = _policy(previous)
    if problems := validate(policy):
        raise PolicyRefused(problems)
    return await _replace_or_conflict(session, policy, expected_version, via, by)


@contextmanager
def _without_row_values() -> Generator[None]:
    """Turn a database error into ``SettingsStoreFailure``.

    SQLAlchemy and PostgreSQL put the bound parameters and the failing row (zone included) into the error text; the
    original error is dropped (``from None``) so no logger or error report can print it (AC-33). The class named is
    the driver's (``UndefinedTableError``); SQLAlchemy's own wrapper class only says ``ProgrammingError``.
    """
    try:
        yield
    except DBAPIError as error:
        driver_error = (error.orig.__cause__ or error.orig) if error.orig is not None else error
        raise SettingsStoreFailure(type(driver_error).__name__, getattr(error.orig, "sqlstate", None)) from None


class PgSettingsStore:
    """Satisfies ``SettingsStore``; every method is one short transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def read(self) -> StoredSettings | None:
        """The stored row, or None when none was ever written.

        Raises:
            StoredSettingsInvalid: the row exists but fails ``validate``; it is never returned as a policy.
            SettingsStoreFailure: the database could not answer (class and SQLSTATE only, never the SQL).
        """
        row = await self._row()
        if row is None:
            return None
        if rules := _broken_rules(row):
            raise StoredSettingsInvalid(rules)
        return _stored(row)

    async def read_for_dialogue(self) -> SettingsView:
        """The version and policy of the row for the settings dialogue; an invalid row is reported with its version.

        The dialogue needs the version of an invalid row to write a whole new row over it. ``read`` stays strict for
        the policy source.

        Raises:
            SettingsStoreFailure: the database could not answer (class and SQLSTATE only, never the SQL).
        """
        row = await self._row()
        if row is None:
            return SettingsView(0, None)
        if rules := _broken_rules(row):
            return SettingsView(row.version, None, rules)
        return SettingsView(row.version, _stored(row).policy)

    async def _row(self) -> Schedule | None:
        with _without_row_values():
            async with self._sessions() as session:
                return await session.get(Schedule, ROW)

    async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
        """Replace the whole row if it is still at ``expected_version`` (0 = insert the first row).

        Raises:
            PolicyRefused: the policy breaks a rule; the database was not touched.
            VersionConflict: the row is not at ``expected_version``; nothing was written.
        """
        if problems := validate(policy):
            raise PolicyRefused(problems)
        with _without_row_values():
            async with self._sessions.begin() as session:
                return await _replace_or_conflict(session, policy, expected_version, via, by)

    async def undo(self, expected_version: int, via: str, by: str) -> StoredSettings:
        """Put back the values the change to ``expected_version`` replaced, as a new audited write.

        Raises:
            VersionConflict: the row is not at ``expected_version`` (or does not exist); nothing changed.
            NothingToUndo: ``expected_version`` is the first write, which replaced nothing.
            PolicyRefused: the previous values no longer pass validation (for example a zone the tz database dropped).
        """
        with _without_row_values():
            async with self._sessions.begin() as session:
                return await _undo_in(session, expected_version, via, by)
