"""Tables of the mail-triage agent (design "Data model").

No table has a column for a mail body: the agent keeps ids, states, hashes and decisions, never mail text (AC-22). The
one exception is ``draft.body``, the reply Marco has written himself, which is needed until he confirms or cancels it.
"""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003  # SQLAlchemy reads the annotations at runtime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
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
    awaiting_input: Mapped[str | None] = mapped_column(String(16))  # what Marco is asked to type next
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
    """Where the last Gmail poll stopped (a single row)."""

    __tablename__ = "poll_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    history_id: Mapped[str | None] = mapped_column(String(32))
