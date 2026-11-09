"""The PostgreSQL store behind the use cases: one class that satisfies their store ports (ADR-0020).

Every method is one short transaction. Alert ids in the use cases are strings; here they are the numeric primary key,
and anything that is not a number is simply an unknown alert. The store never writes mail bodies.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.alert_state import AlertState
from app.core.alert_text import AuthResults, MailMeta
from app.core.judgement import Judgement
from app.db import repos
from app.db.models import Alert, CatchupState, Draft, MailItem, OverviewLog, PollState
from app.db.pg_conversation import ConversationStore, Kind
from app.usecases.catchup import CatchUpState
from app.usecases.deliver_alerts import PendingAlert
from app.usecases.overview import FiledMail
from app.usecases.reply import AlertInfo, StoredDraft
from app.usecases.triage import Claim, Outcome

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

POLL_ROW = 1
_QUESTIONS: dict[str, tuple[Kind, str]] = {"snooze_hours": ("snooze", "hours"), "reply_text": ("reply", "text")}
_KINDS = {(kind, step): name for name, (kind, step) in _QUESTIONS.items()}
REMOVED = "(removed after 30 days)"


def _id(alert_id: str) -> int | None:
    return int(alert_id) if alert_id.isascii() and alert_id.isdigit() else None


def _pending(alert: Alert, item: MailItem) -> PendingAlert:
    judgement = Judgement(
        category=(item.label or "").removeprefix("Assistant/"),
        urgent=True,
        reason=item.reason or "",
        summary=item.summary or "",
        confidence=item.confidence or 0.0,
    )
    meta = MailMeta(
        sender=item.sender or REMOVED,
        subject=item.subject or REMOVED,
        reply_to=item.reply_to,
        has_attachment=item.has_attachment,
    )
    auth = AuthResults(item.auth_spf, item.auth_dkim, item.auth_dmarc)
    return PendingAlert(str(alert.id), AlertState(alert.state), meta, judgement, auth)


def _stored(draft: Draft) -> StoredDraft:
    return StoredDraft(
        draft_id=draft.id,
        alert_id=str(draft.alert_id),
        recipient=draft.recipient,
        body=draft.body,
        digest=draft.digest,
        expires_at=draft.expires_at,
        used=draft.used,
    )


class PgStore:
    """Triage, delivery, snooze, reply and overview storage in PostgreSQL."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Keep the session factory; the pending question lives in the conversation row."""
        self._sessions = sessions
        self._conversations = ConversationStore(sessions, lambda: datetime.now(UTC))

    # ---- triage pipeline -------------------------------------------------------------------------------------

    async def history_id(self) -> str | None:
        """The stored Gmail history position."""
        async with self._sessions() as session:
            row = await session.get(PollState, POLL_ROW)
        return row.history_id if row else None

    async def save_history_id(self, value: str) -> None:
        """Store the new position."""
        statement = insert(PollState).values(id=POLL_ROW, history_id=value)
        statement = statement.on_conflict_do_update(index_elements=["id"], set_={"history_id": value})
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def claim(self, message_id: str, thread_id: str) -> Claim:
        """``NEW`` for the first caller, ``PENDING`` for a claim never completed, ``DONE`` otherwise."""
        async with self._sessions.begin() as session:
            if await repos.try_claim(session, message_id, thread_id):
                return Claim.NEW
            item = (await session.execute(select(MailItem).where(MailItem.gmail_message_id == message_id))).scalar_one()
            return Claim.DONE if item.completed or item.abandoned else Claim.PENDING

    async def known_labels(self) -> list[str]:
        """Category labels in use."""
        async with self._sessions() as session:
            rows = await session.execute(select(MailItem.label).where(MailItem.label.is_not(None)).distinct())
        return [label for (label,) in rows if label]

    async def complete(self, message_id: str, outcome: Outcome) -> None:
        """Record label, urgency, content and the alert (when there is one) in one transaction."""
        await self._complete(message_id, outcome, backlog=False)

    async def complete_backlog(self, message_id: str, outcome: Outcome) -> None:
        """Like ``complete``, for a mail of the one-time catch-up: it is flagged so its alerts can be counted."""
        await self._complete(message_id, outcome, backlog=True)

    async def _complete(self, message_id: str, outcome: Outcome, *, backlog: bool) -> None:
        now, content = datetime.now(UTC), outcome.content
        values = {
            "label": outcome.label,
            "urgent": outcome.urgent,
            "confidence": outcome.confidence,
            "note": outcome.note or None,
            "completed": True,
            "backlog": backlog,
            "sender": content.sender,
            "subject": content.subject,
            "reply_to": content.reply_to,
            "reason": content.reason,
            "summary": content.summary,
            "has_attachment": content.has_attachment,
            "auth_spf": content.auth.spf,
            "auth_dkim": content.auth.dkim,
            "auth_dmarc": content.auth.dmarc,
        }
        async with self._sessions.begin() as session:
            statement = update(MailItem).where(MailItem.gmail_message_id == message_id).values(**values)
            item_id = (await session.execute(statement.returning(MailItem.id))).scalar_one()
            if (
                outcome.alert is not None
                and await session.scalar(select(Alert.id).where(Alert.mail_item_id == item_id)) is None
            ):
                session.add(Alert(mail_item_id=item_id, state=outcome.alert.value, created_at=now, updated_at=now))

    # ---- one-time catch-up of old unread mail (INT-003) -------------------------------------------------------

    async def catchup_state(self) -> CatchUpState | None:
        """When the catch-up started and finished; ``None`` when it never started."""
        async with self._sessions() as session:
            row = await session.get(CatchupState, 1)
        return CatchUpState(row.started_at, row.finished_at) if row else None

    async def start_catchup(self, at: datetime) -> None:
        """Store the cut-off. A second call, also a racing one, keeps the first time."""
        statement = insert(CatchupState).values(id=1, started_at=at).on_conflict_do_nothing()
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def finish_catchup(self, at: datetime) -> None:
        """Mark the catch-up done. A second call keeps the first time."""
        statement = (
            update(CatchupState).where(CatchupState.id == 1, CatchupState.finished_at.is_(None)).values(finished_at=at)
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def backlog_alerts(self) -> int:
        """How many alerts the catch-up created, in any state."""
        statement = (
            select(func.count(Alert.id))
            .join(MailItem, MailItem.id == Alert.mail_item_id)
            .where(MailItem.backlog.is_(True))
        )
        async with self._sessions() as session:
            return int((await session.execute(statement)).scalar_one())

    async def record_failure(self, message_id: str) -> int:
        """Count one more failed attempt and return the total."""
        statement = (
            update(MailItem)
            .where(MailItem.gmail_message_id == message_id)
            .values(failures=MailItem.failures + 1)
            .returning(MailItem.failures)
        )
        async with self._sessions.begin() as session:
            return (await session.execute(statement)).scalar_one()

    async def abandon(self, message_id: str) -> None:
        """Stop retrying this mail."""
        async with self._sessions.begin() as session:
            await session.execute(
                update(MailItem).where(MailItem.gmail_message_id == message_id).values(abandoned=True)
            )

    # ---- alert delivery --------------------------------------------------------------------------------------

    async def _alerts(self, *conditions: object) -> list[PendingAlert]:
        statement = select(Alert, MailItem).join(MailItem, MailItem.id == Alert.mail_item_id).where(*conditions)  # type: ignore[arg-type]
        async with self._sessions() as session:
            rows = (await session.execute(statement.order_by(Alert.id))).all()
        return [_pending(alert, item) for alert, item in rows]

    async def held(self) -> list[PendingAlert]:
        """Alerts waiting for quiet hours to end."""
        return await self._alerts(Alert.state == AlertState.HELD.value)

    async def unsent(self) -> list[PendingAlert]:
        """Open alerts that have no Telegram message yet."""
        return await self._alerts(Alert.state == AlertState.OPEN.value, Alert.telegram_message_id.is_(None))

    async def release(self, alert_id: str) -> None:
        """Move a held alert to open."""
        await self.set_state(alert_id, AlertState.OPEN)

    async def mark_sent(self, alert_id: str, telegram_message_id: int, *, at: datetime) -> None:
        """Store the Telegram message id; the alert is not sent again."""
        key = _id(alert_id)
        if key is None:
            return
        async with self._sessions.begin() as session:
            await session.execute(
                update(Alert).where(Alert.id == key).values(telegram_message_id=telegram_message_id, sent_at=at)
            )

    async def sent_since(self, since: datetime) -> int:
        """How many alerts were sent since ``since``."""
        async with self._sessions() as session:
            return (
                await session.execute(select(func.count()).select_from(Alert).where(Alert.sent_at >= since))
            ).scalar_one()

    async def record_audit(self, kind: str, alert_id: str, digest: str | None = None) -> None:
        """Write an audit entry: kind, alert id and digest only."""
        async with self._sessions.begin() as session:
            await repos.record_audit(session, kind, ref=alert_id, digest=digest)

    # ---- snooze and alert state ------------------------------------------------------------------------------

    async def state_of(self, alert_id: str) -> AlertState | None:
        """Current state, or ``None`` for an unknown alert."""
        key = _id(alert_id)
        if key is None:
            return None
        async with self._sessions() as session:
            row = await session.get(Alert, key)
        return AlertState(row.state) if row else None

    async def set_state(
        self, alert_id: str, state: AlertState, *, due_at: datetime | None = None, resend: bool = False
    ) -> None:
        """Save the state; ``resend`` forgets the Telegram message so the alert is sent again."""
        key = _id(alert_id)
        if key is None:
            return
        values: dict[str, object] = {"state": state.value, "due_at": due_at, "updated_at": datetime.now(UTC)}
        if resend:
            values |= {"telegram_message_id": None, "sent_at": None}
        async with self._sessions.begin() as session:
            await session.execute(update(Alert).where(Alert.id == key).values(**values))

    async def due_snoozed(self, now: datetime) -> list[str]:
        """Ids of snoozed alerts whose due time has passed."""
        statement = select(Alert.id).where(Alert.state == AlertState.SNOOZED.value, Alert.due_at <= now)
        async with self._sessions() as session:
            return [str(alert_id) for (alert_id,) in await session.execute(statement.order_by(Alert.id))]

    # ---- reply flow ------------------------------------------------------------------------------------------

    async def alert_info(self, alert_id: str) -> AlertInfo | None:
        """State and Gmail message id of an alert."""
        key = _id(alert_id)
        if key is None:
            return None
        statement = select(Alert.state, MailItem.gmail_message_id).join(MailItem).where(Alert.id == key)
        async with self._sessions() as session:
            row = (await session.execute(statement)).first()
        return AlertInfo(AlertState(row[0]), row[1]) if row else None

    async def save_draft(self, draft: StoredDraft) -> None:
        """Store a draft that waits for confirmation."""
        async with self._sessions.begin() as session:
            await repos.save_draft(
                session,
                draft.draft_id,
                alert_id=int(draft.alert_id),
                recipient=draft.recipient,
                body=draft.body,
                digest=draft.digest,
                expires_at=draft.expires_at,
            )

    async def get_draft(self, draft_id: str) -> StoredDraft | None:
        """Read a draft."""
        async with self._sessions() as session:
            row = await session.get(Draft, draft_id)
        return _stored(row) if row else None

    async def consume_draft(self, draft_id: str, digest: str, *, now: datetime) -> StoredDraft | None:
        """Mark a draft used if it is unused, unexpired and matches; atomic."""
        async with self._sessions.begin() as session:
            row = await repos.consume_draft(session, draft_id, digest, now=now)
            return _stored(row) if row else None

    async def invalidate_drafts(self, alert_id: str) -> None:
        """Mark every draft of the alert as used."""
        key = _id(alert_id)
        if key is None:
            return
        async with self._sessions.begin() as session:
            await session.execute(update(Draft).where(Draft.alert_id == key).values(used=True))

    async def set_awaiting(self, alert_id: str, kind: str | None) -> None:
        """Remember what Marco is asked to type next for this alert; ``None`` clears it if it is this alert's."""
        if _id(alert_id) is None:
            return
        if kind is None:
            await self._conversations.clear_for(alert_id)
            return
        dialogue, step = _QUESTIONS[kind]
        await self._conversations.start(dialogue, alert_id, step, {}, None)

    async def awaiting(self) -> tuple[str, str] | None:
        """The alert Marco is expected to type something for, with the kind of input."""
        current = await self._conversations.current()
        if current is None or current.target is None or (current.kind, current.step) not in _KINDS:
            return None
        return current.target, _KINDS[current.kind, current.step]

    # ---- daily overview and retention ------------------------------------------------------------------------

    async def filed_without_alert_since(self, since: datetime) -> list[FiledMail]:
        """Mails filed since ``since`` that did not raise an alert."""
        statement = (
            select(MailItem)
            .outerjoin(Alert, Alert.mail_item_id == MailItem.id)
            .where(MailItem.completed.is_(True), MailItem.created_at >= since, Alert.id.is_(None))
            .order_by(MailItem.id)
        )
        async with self._sessions() as session:
            items = (await session.execute(statement)).scalars().all()
        return [
            FiledMail(i.label or "", i.confidence or 0.0, i.sender or REMOVED, i.subject or REMOVED, urgent=i.urgent)
            for i in items
        ]

    async def overview_sent(self, day: date) -> bool:
        """Whether the overview of this day was settled."""
        async with self._sessions() as session:
            return await session.get(OverviewLog, day) is not None

    async def mark_overview_sent(self, day: date) -> None:
        """Remember that the overview of this day was settled."""
        statement = insert(OverviewLog).values(day=day, settled_at=datetime.now(UTC)).on_conflict_do_nothing()
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def purge_content(self, before: datetime) -> int:
        """Clear the mail-derived content of mail claimed before ``before``; ids and decisions stay."""
        cleared = dict.fromkeys(("sender", "subject", "reply_to", "reason", "summary"))
        statement = (
            update(MailItem)
            .where(MailItem.created_at < before, MailItem.sender.is_not(None))
            .values(**cleared)
            .returning(MailItem.id)
        )
        async with self._sessions.begin() as session:
            return len((await session.execute(statement)).all())
