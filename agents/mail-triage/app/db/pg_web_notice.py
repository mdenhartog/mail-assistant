"""The web notice in PostgreSQL: the audit records of web changes, the cursor and the token records (ADR-0033).

A web change is an audit record whose ``db_role`` is the web login role. ``db_role`` is set by the audit trigger from
``session_user``, so the writer cannot choose it; the actor text (``by``) is never used to decide. The version is
read as an integer, never as text, so version 10 comes after version 9. The agent role may read ``settings_change``,
read and write ``poll_state`` and read, write and delete ``web_notice_token`` (``app/db/grants.sql``) and nothing more.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import Integer, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import PollState, SettingsChange, WebNoticeToken
from app.db.pg_update_cursor import POLL_ROW
from app.usecases.web_notice import NoticeToken, OpenBurst, WebChange
from schedule_policy.policy import TimePolicy

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
            burst_id=token.burst_id,
            first_version=token.first_version,
        )
        async with self._sessions.begin() as session:
            session.add(record)

    async def find(self, token: str) -> NoticeToken | None:
        """The record of ``token`` (expired or not); ``None`` when there is none."""
        async with self._sessions() as session:
            row = await session.get(WebNoticeToken, token)
        if row is None:
            return None
        return NoticeToken(
            row.token, row.version, dict(row.before), row.created_at, row.expires_at, row.burst_id, row.first_version
        )

    async def open_burst(self, after: int, now: datetime) -> OpenBurst | None:
        """The burst of the lowest unexpired token record above version ``after``; ``None`` when there is none."""
        statement = (
            select(WebNoticeToken.burst_id, WebNoticeToken.first_version, WebNoticeToken.before)
            .where(WebNoticeToken.version > after, WebNoticeToken.expires_at > now)
            .order_by(WebNoticeToken.version, WebNoticeToken.created_at)
            .limit(1)
        )
        async with self._sessions() as session:
            row = (await session.execute(statement)).first()
        return None if row is None else OpenBurst(row.burst_id, row.first_version, dict(row.before))

    async def burst_end(self, burst_id: str, first_version: int) -> int:
        """The highest announced version among the tokens of the burst ``burst_id`` (0 when none)."""
        statement = select(func.max(WebNoticeToken.version)).where(
            WebNoticeToken.burst_id == burst_id, WebNoticeToken.version >= first_version
        )
        async with self._sessions() as session:
            return (await session.execute(statement)).scalar_one() or 0

    async def consume(self, token: str) -> bool:
        """Delete the record of ``token``; ``True`` when this call deleted it (a second call gets ``False``)."""
        statement = delete(WebNoticeToken).where(WebNoticeToken.token == token).returning(WebNoticeToken.token)
        async with self._sessions.begin() as session:
            deleted = await session.execute(statement)
        return deleted.first() is not None

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
