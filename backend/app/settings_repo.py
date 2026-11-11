"""Read access to ``settings.schedule`` as the web role (U-web-settings-20); the write part is U-web-settings-21."""

from dataclasses import dataclass
from datetime import datetime

from app.db import Database
from schedule_policy.policy import TimePolicy


@dataclass(frozen=True, slots=True)
class StoredSettings:
    """The schedule row as the page sees it; ``version`` 0 means no row yet (defaults)."""

    policy: TimePolicy
    version: int
    updated_at: datetime | None
    updated_via: str | None


class SettingsRepository:
    """Reads the single schedule row."""

    def __init__(self, database: Database) -> None:
        """Keep the database access."""
        self._database = database

    async def read(self) -> StoredSettings:
        """Return the stored settings, or the defaults at version 0."""
        raise NotImplementedError
