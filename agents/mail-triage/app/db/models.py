"""Tables of the mail-triage agent (design "Data model").

No table has a column for a mail body: the agent keeps ids, states, hashes and decisions, never mail text (AC-22). The
one exception is ``draft.body``, the reply Marco has written himself, which is needed until he confirms or cancels it.
"""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003  # SQLAlchemy reads the annotations at runtime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base of all tables."""


class MailItem(Base):
    """One row per Gmail message the agent has claimed."""

    __tablename__ = "mail_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    gmail_message_id: Mapped[str] = mapped_column(String(64), unique=True)
    thread_id: Mapped[str] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(80))
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Capped mail-derived content for alerts and the overview, cleared after 30 days (ADR-0020). Never the body.
    sender: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(300))
    reply_to: Mapped[str | None] = mapped_column(String(320))
    reason: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(400))
    has_attachment: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    auth_spf: Mapped[str | None] = mapped_column(String(16))
    auth_dkim: Mapped[str | None] = mapped_column(String(16))
    auth_dmarc: Mapped[str | None] = mapped_column(String(16))
    # Filed by the one-time catch-up of old unread mail (INT-003), so its alerts can be counted.
    backlog: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Progress of the pipeline for this mail.
    note: Mapped[str | None] = mapped_column(String(80))
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    abandoned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class OverviewLog(Base):
    """One row per day whose overview was settled (sent, or skipped because nothing was filed)."""

    __tablename__ = "overview_log"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Alert(Base):
    """State of the alert for one mail."""

    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(primary_key=True)
    mail_item_id: Mapped[int] = mapped_column(ForeignKey("mail_item.id"), unique=True)
    state: Mapped[str] = mapped_column(String(16))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When a held alert may be delivered: the quiet end under the policy valid when it was held (INT-002).
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Draft(Base):
    """A reply Marco has written and has not yet confirmed or cancelled."""

    __tablename__ = "draft"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alert.id"))
    recipient: Mapped[str | None] = mapped_column(String(320))
    body: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """What happened and when: ids, hashes and decisions, never mail text."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(32))
    mail_item_id: Mapped[int | None] = mapped_column(Integer)
    ref: Mapped[str | None] = mapped_column(String(64))
    digest: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(String(200))


class OAuthToken(Base):
    """The encrypted Gmail refresh token (a single row)."""

    __tablename__ = "oauth_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PollState(Base):
    """Where the last Gmail poll stopped and the last Telegram update that was handled (a single row)."""

    __tablename__ = "poll_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    history_id: Mapped[str | None] = mapped_column(String(32))
    telegram_update_id: Mapped[int | None] = mapped_column(BigInteger)
    web_notice_version: Mapped[int | None] = mapped_column(Integer)  # last announced web change (ADR-0033)


class CatchupState(Base):
    """When the one-time catch-up of old unread mail started and finished (a single row, INT-003)."""

    __tablename__ = "catchup_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_catchup_state_single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Schedule(Base):
    """The one row of adjustable times: quiet hours, daily overview, reminder default, zone (ADR-0025)."""

    __tablename__ = "schedule"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_schedule_single_row"),
        CheckConstraint(
            "quiet_start BETWEEN 0 AND 1439 AND quiet_end BETWEEN 0 AND 1439 "
            "AND overview_at BETWEEN 0 AND 1439 AND remind_at BETWEEN 0 AND 1439",
            name="ck_schedule_minutes_range",
        ),
        CheckConstraint("quiet_start <> quiet_end", name="ck_schedule_quiet_distinct"),
        CheckConstraint(
            "((quiet_end - quiet_start + 1440) % 1440) BETWEEN 60 AND 720", name="ck_schedule_window_length"
        ),
        CheckConstraint(
            "((overview_at - quiet_start + 1440) % 1440) >= ((quiet_end - quiet_start + 1440) % 1440)",
            name="ck_schedule_overview_outside",
        ),
        CheckConstraint(
            "((remind_at - quiet_start + 1440) % 1440) >= ((quiet_end - quiet_start + 1440) % 1440)",
            name="ck_schedule_remind_outside",
        ),
        CheckConstraint("zone ~ '^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$'", name="ck_schedule_zone_pattern"),
        CheckConstraint("updated_via IN ('telegram', 'web')", name="ck_schedule_updated_via"),
        {"schema": "settings"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    zone: Mapped[str] = mapped_column(Text)
    quiet_start: Mapped[int] = mapped_column(SmallInteger)  # minutes after midnight
    quiet_end: Mapped[int] = mapped_column(SmallInteger)
    overview_at: Mapped[int] = mapped_column(SmallInteger)
    remind_at: Mapped[int] = mapped_column(SmallInteger)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_via: Mapped[str] = mapped_column(String(16))
    updated_by: Mapped[str] = mapped_column(String(64))


class SettingsChange(Base):
    """Append-only record of every change to the schedule, written by a database trigger (AC-30). No free text."""

    __tablename__ = "settings_change"
    __table_args__ = ({"schema": "settings"},)
    # The table has no key (rows are never addressed); the mapper only needs to be told which columns identify a row.
    __mapper_args__ = {"primary_key": ["at", "via", "by"]}  # noqa: RUF012

    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    via: Mapped[str] = mapped_column(String(16))
    by: Mapped[str] = mapped_column(String(64))
    db_role: Mapped[str] = mapped_column(String(63))  # session_user of the writer, set by the trigger
    old: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    new: Mapped[dict[str, object]] = mapped_column(JSONB)


class Conversation(Base):
    """The pending Telegram dialogue, if any (a single row, ADR-0026)."""

    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_conversation_single_row"),
        CheckConstraint("kind IN ('snooze', 'reply', 'settings')", name="ck_conversation_kind"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # snooze, reply or settings
    target: Mapped[str | None] = mapped_column(String(64))
    step: Mapped[str] = mapped_column(String(32))
    partial: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    nonce: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


_SECURITY_EVENT_KINDS = (
    "code_refused",
    "code_request_refused",
    "mail_failed",
    "session_start",
    "session_end",
    "csrf_refused",
    "rate_limited",
    "lock_refused",
)


class LoginRequest(Base):
    """An e-mailed sign-in code in flight (ADR-0036): only a keyed hash of the code, dead rows kept for an hour."""

    __tablename__ = "login_request"
    __table_args__ = (
        CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_login_request_attempts"),
        {"schema": "web_auth"},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username_key: Mapped[str] = mapped_column(CHAR(64))
    code_hash: Mapped[str] = mapped_column(CHAR(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # the request time starts the cooldown
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # empty when the send failed
    dead_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebSession(Base):
    """A web session: the session id and the username are stored as hashes only."""

    __tablename__ = "session"
    __table_args__ = ({"schema": "web_auth"},)

    id_hash: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    username_hash: Mapped[str] = mapped_column(CHAR(64))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SecurityEvent(Base):
    """One security event per kind, client and window; no free text."""

    __tablename__ = "security_event"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{kind}'" for kind in _SECURITY_EVENT_KINDS) + ")", name="ck_security_event_kind"
        ),
        CheckConstraint("result IN ('ok', 'refused', 'failed')", name="ck_security_event_result"),
        UniqueConstraint("kind", "client_key", "window", name="uq_security_event_kind_client_window"),
        {"schema": "web_auth"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    kind: Mapped[str] = mapped_column(String(24))
    result: Mapped[str] = mapped_column(String(16))
    username_hash: Mapped[str | None] = mapped_column(CHAR(64))
    request_id: Mapped[str] = mapped_column(String(64))
    client_key: Mapped[str] = mapped_column(String(64))
    window: Mapped[int] = mapped_column(BigInteger)


class WebLock(Base):
    """The single row that locks web sign-in (ADR-0033); set by the agent, cleared from Telegram."""

    __tablename__ = "web_lock"
    __table_args__ = (CheckConstraint("id = 1", name="ck_web_lock_single_row"), {"schema": "web_auth"})

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WebNoticeToken(Base):
    """The own short-lived Undo token of a web notice (ADR-0033); not the conversation row."""

    __tablename__ = "web_notice_token"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)  # the announced change
    before: Mapped[dict[str, object]] = mapped_column(JSONB)  # the values Undo restores
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    burst_id: Mapped[str] = mapped_column(String(64), index=True)  # the same for every notice of one burst
    first_version: Mapped[int] = mapped_column(Integer)  # the first change of the burst
