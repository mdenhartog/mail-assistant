"""The web notice in PostgreSQL: the audit records of web changes, the cursor and the token records (ADR-0033).

A web change is an audit record whose ``db_role`` is the web login role. ``db_role`` is set by the audit trigger from
``session_user``, so the writer cannot choose it; the actor text (``by``) is never used to decide. The version is
read as an integer, never as text, so version 10 comes after version 9. The agent role may read ``settings_change``,
read and write ``poll_state`` and write ``web_notice_token`` (``app/db/grants.sql``) and nothing more.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import Integer, func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import PollState, SettingsChange, WebNoticeToken
from app.db.pg_update_cursor import POLL_ROW
from app.usecases.web_notice import WebChange
from schedule_policy.policy import TimePolicy

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.usecases.web_notice import NoticeToken

WEB_ROLE: Final = "web_settings_runtime"  # the database login of the api; the audit trigger records it as ``db_role``
_version_int = SettingsChange.new["version"].astext.cast(Integer)


def _clock(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _policy(image: Mapping[str, Any]) -> TimePolicy:
    """The policy in the ``old`` or ``new`` image of an audit record (the column names of the schedule row)."""
    return TimePolicy(
        zone=image["zone"],
        quiet_start=_clock(image["quiet_start"]),
        quiet_end=_clock(image["quiet_end"]),
        overview_at=_clock(image["overview_at"]),
        remind_at=_clock(image["remind_at"]),
    )


class PgWebNotice:
    """Satisfies ``NoticeStore``; every call is one short transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory."""
        self._sessions = sessions

    async def last_announced(self) -> int:
        """The version of the last announced web change, 0 when none was announced."""
        async with self._sessions() as session:
            row = await session.get(PollState, POLL_ROW)
        return (row.web_notice_version if row else None) or 0

    async def pending_after(self, version: int) -> list[WebChange]:
        """Web changes above ``version``, lowest version first (by the integer, not by its text)."""
        statement = (
            select(SettingsChange.at, SettingsChange.old, SettingsChange.new)
            .where(SettingsChange.db_role == WEB_ROLE, _version_int > version)
            .order_by(_version_int)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            WebChange(int(new["version"]), at, _policy(old) if old is not None else None, _policy(new))  # type: ignore[arg-type]
            for at, old, new in rows
        ]

    async def record_token(self, token: NoticeToken) -> None:
        """Store the token record of a notice."""
        record = WebNoticeToken(
            token=token.token,
            version=token.version,
            before=token.before,
            created_at=token.created_at,
            expires_at=token.expires_at,
        )
        async with self._sessions.begin() as session:
            session.add(record)

    async def advance(self, version: int) -> None:
        """Move the cursor to ``version`` unless it is already higher; the other columns of the row stay."""
        statement = insert(PollState).values(id=POLL_ROW, web_notice_version=version)
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "web_notice_version": func.greatest(
                    func.coalesce(PollState.web_notice_version, 0), statement.excluded.web_notice_version
                )
            },
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)
