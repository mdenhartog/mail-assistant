"""PolicySource on the settings store: validated policy, last good values and defaults as the fallback (C-9).

A bad read never stops the agent: it keeps working with the last good values of this process, or the defaults, and
Marco is told once per incident. Logs carry the rule ids or the error class (and SQLSTATE), never a stored value
(threat model T-6, T-9; AC-33).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.exc import DBAPIError

from app.db.repos import StoredSettingsInvalid
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.db.repos import StoredSettings
    from app.usecases.policy_notice import PolicyNotice

    type Deadline = Callable[[Awaitable[StoredSettings | None], float], Awaitable[StoredSettings | None]]

logger = logging.getLogger(__name__)

READ_TIMEOUT_SECONDS = 2.0


class SettingsReader(Protocol):
    """The one thing this source needs from the settings store."""

    async def read(self) -> StoredSettings | None:
        """The stored row, or None when none was ever written."""
        ...


def _describe(error: Exception) -> str:
    """The error class and, for a database error, its SQLSTATE: what is safe to log (no parameters, no row values)."""
    if isinstance(error, DBAPIError) and error.orig is not None:
        driver_error = error.orig.__cause__ or error.orig  # the asyncpg class names the fault; SQLAlchemy's is generic
        return f"{type(driver_error).__name__} sqlstate={getattr(error.orig, 'sqlstate', None)}"
    return type(error).__name__


class PgPolicySource:
    """Satisfies ``PolicySource``."""

    def __init__(
        self,
        store: SettingsReader,
        notice: PolicyNotice,
        deadline: Deadline = asyncio.wait_for,
    ) -> None:
        """Keep the store, the notice and the deadline seam (tests pass one that needs no real waiting)."""
        self._store = store
        self._notice = notice
        self._deadline = deadline
        self._last_good: TimePolicy | None = None

    async def current(self) -> TimePolicy:
        """The stored policy; the last good one or the defaults when the row cannot be read or is invalid."""
        try:
            stored = await self._deadline(self._store.read(), READ_TIMEOUT_SECONDS)
        except StoredSettingsInvalid as invalid:
            logger.warning("settings_invalid rules=%s", ",".join(invalid.rules))
            return await self._fall_back("the saved settings are not valid")
        except Exception as error:  # the agent must keep alerting whatever the database does
            logger.warning("settings_unreadable error=%s", _describe(error))
            return await self._fall_back("the settings cannot be read")
        self._last_good = DEFAULT_POLICY if stored is None else stored.policy
        self._notice.recovered()
        return self._last_good

    async def _fall_back(self, reason: str) -> TimePolicy:
        in_use = self._last_good or DEFAULT_POLICY
        await self._notice.incident(in_use, reason)
        return in_use
