"""Stub of the security event reader (U-web-settings-48)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class PgSecurityEvents:
    """Stub."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def refused_codes(self, since: datetime) -> int:
        """Stub."""
        raise NotImplementedError
