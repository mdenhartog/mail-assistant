"""The security events of the web app, read by the agent (U-web-settings-48; ADR-0033, ADR-0039).

The agent role may only ``SELECT`` on ``web_auth.security_event`` (``app/db/grants.sql``): it cannot write an event and
it has no access to ``session`` or ``login_request``. Only counts leave this module: never a client key, a username
digest or a request id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import func, select

from app.db.models import SecurityEvent

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

CODE_REFUSED: Final = "code_refused"  # a wrong or expired code; the only kind that is counted


class PgSecurityEvents:
    """Satisfies ``EventSource``; every call is one short read."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def refused_codes(self, since: datetime, after_id: int) -> int:
        """Sum of ``count`` of the ``code_refused`` events newer than ``since`` with an id above ``after_id``.

        0 when there are none. ``after_id`` is how events that were already acted on stay out of the sum.
        """
        statement = select(func.coalesce(func.sum(SecurityEvent.count), 0)).where(
            SecurityEvent.kind == CODE_REFUSED, SecurityEvent.at > since, SecurityEvent.id > after_id
        )
        async with self._sessions() as session:
            return int((await session.execute(statement)).scalar_one())

    async def newest_id(self) -> int:
        """The highest event id of any kind (0 when there are no events); ids only go up."""
        async with self._sessions() as session:
            return int((await session.execute(select(func.coalesce(func.max(SecurityEvent.id), 0)))).scalar_one())
