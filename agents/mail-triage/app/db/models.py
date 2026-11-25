"""Tables of the mail-triage agent (design "Data model").

No table has a column for a mail body: the agent keeps ids, states, hashes and decisions, never mail text (AC-22). The
one exception is ``draft.body``, the reply Marco has written himself, which is needed until he confirms or cancels it.
"""

from __future__ import annotations

import uuid  # SQLAlchemy reads the annotations at runtime
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
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    auth_dmarc: Mapped[str | None] = mapped_column(String(16))  # no longer written (the weaker parse); dropped later
    # The From domain Gmail vouches for (``authenticated_from_domain``); ``None`` when it does not (ADR-0054).
    verified_domain: Mapped[str | None] = mapped_column(String(255))
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
    # Why the alert exists (ADR-0057): ``urgent`` and ``always_notify:<category>``; ``None`` for an alert from before.
    causes: Mapped[list[str] | None] = mapped_column(JSONB)
    # A sender rule filed the mail, so the model never read it and the alert shows no summary.
    by_rule: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


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
    list_notice_version: Mapped[int | None] = mapped_column(Integer)  # last announced category list version (0017)


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
        CheckConstraint("label_wait_minutes BETWEEN 5 AND 720", name="ck_schedule_label_wait"),
        CheckConstraint("label_protection_days BETWEEN 1 AND 30", name="ck_schedule_label_protection"),
        CheckConstraint("label_retention_days BETWEEN 7 AND 90", name="ck_schedule_label_retention"),
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
    # Label cleanup (0030, ADR-0060 point 6); the bounds are those of ``category_policy.settings``.
    label_wait_minutes: Mapped[int] = mapped_column(SmallInteger, server_default="720")
    label_protection_days: Mapped[int] = mapped_column(SmallInteger, server_default="7")
    label_retention_days: Mapped[int] = mapped_column(SmallInteger, server_default="30")


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
    "code_invalid",
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
    client_hash: Mapped[str] = mapped_column(CHAR(64))  # keyed digest of the client key (ADR-0039), never an address
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
        CheckConstraint("count >= 1", name="ck_security_event_count"),
        UniqueConstraint("kind", "client_key", "window", name="uq_security_event_kind_client_window"),
        Index("ix_security_event_kind_at", "kind", "at"),  # the alert query: one kind, newer than a time
        {"schema": "web_auth"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    kind: Mapped[str] = mapped_column(String(24))
    result: Mapped[str] = mapped_column(String(16))
    username_hash: Mapped[str | None] = mapped_column(CHAR(64))
    request_id: Mapped[str] = mapped_column(String(64))
    client_key: Mapped[str] = mapped_column(String(64))
    window: Mapped[int] = mapped_column(BigInteger)
    count: Mapped[int] = mapped_column(Integer, server_default=text("1"))


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


# --- Mail categories, list half (INT-004, ADR-0042, ADR-0043): schema ``categories``, migration 0014 ------------------
# Every table has the mailbox id first in its key. The nil UUID (``OTHER_ID``) stands for the built-in "Other".
OTHER_ID = uuid.UUID(int=0)


class CategoryMailbox(Base):
    """The id of a mailbox and nothing else: the foreign-key target of every categories table."""

    __tablename__ = "mailbox"
    __table_args__ = ({"schema": "categories"},)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)


class CategoryIdentity(Base):
    """The stable id of a category, kept across renames."""

    __tablename__ = "category_identity"
    __table_args__ = ({"schema": "categories"},)

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class ListVersion(Base):
    """One version of the category list; ``created_*`` are derived by a trigger, never supplied (ADR-0030)."""

    __tablename__ = "list_version"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_list_version_positive"),
        CheckConstraint("created_via IN ('telegram', 'web', 'operator')", name="ck_list_version_via"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    created_via: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[str] = mapped_column(CHAR(64))


class Category(Base):
    """A category of one list version. Insert-only: a change of the list is a new version."""

    __tablename__ = "category"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mailbox_id", "version"],
            ["categories.list_version.mailbox_id", "categories.list_version.version"],
            name="fk_category_list_version",
        ),
        ForeignKeyConstraint(
            ["mailbox_id", "id"],
            ["categories.category_identity.mailbox_id", "categories.category_identity.id"],
            name="fk_category_identity",
        ),
        UniqueConstraint("mailbox_id", "version", "position", name="uq_category_position"),
        UniqueConstraint("mailbox_id", "version", "name", name="uq_category_name"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 255", name="ck_category_name_length"),
        CheckConstraint("char_length(description) <= 1500", name="ck_category_description_length"),
        CheckConstraint("position BETWEEN 0 AND 99", name="ck_category_position"),
        CheckConstraint("kind IN ('topic', 'extra')", name="ck_category_kind"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default="")
    position: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str] = mapped_column(String(8), server_default="topic")  # migration 0024
    notify: Mapped[bool] = mapped_column(Boolean, server_default=false())  # migration 0024


class ListAudit(Base):
    """Who changed the list, from which list to which; written by a deferred SECURITY DEFINER trigger."""

    __tablename__ = "list_audit"
    __table_args__ = ({"schema": "categories"},)

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    old_list: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    new_list: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    old_instructions: Mapped[str] = mapped_column(Text, server_default="")  # migration 0028
    new_instructions: Mapped[str] = mapped_column(Text, server_default="")  # migration 0028
    channel: Mapped[str] = mapped_column(String(16))
    actor_digest: Mapped[str] = mapped_column(CHAR(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class CategoryCount(Base):
    """The number of mails per category, replaced each cycle by the agent; ``OTHER_ID`` is "Other"."""

    __tablename__ = "category_count"
    __table_args__ = (CheckConstraint("mail_count >= 0", name="ck_category_count_positive"), {"schema": "categories"})

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    mail_count: Mapped[int] = mapped_column(Integer)
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SenderSkip(Base):
    """How often a listed sender was skipped because Gmail did not vouch for it, per list entry."""

    __tablename__ = "sender_skip"
    __table_args__ = (
        CheckConstraint("skipped >= 1", name="ck_sender_skip_positive"),
        CheckConstraint("char_length(entry) BETWEEN 1 AND 320", name="ck_sender_skip_entry_length"),
        Index("ix_sender_skip_last_skipped_at", "last_skipped_at"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    entry: Mapped[str] = mapped_column(Text, primary_key=True)
    skipped: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    last_skipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class GmailLabel(Base):
    """The name of an ``Assistant/`` label that exists in Gmail (names only), replaced each cycle."""

    __tablename__ = "gmail_label"
    __table_args__ = ({"schema": "categories"},)

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class CategoryLabel(Base):
    """The Gmail label of a category, by the stable category id."""

    __tablename__ = "category_label"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mailbox_id", "category_id"],
            ["categories.category_identity.mailbox_id", "categories.category_identity.id"],
            name="fk_category_label_identity",
        ),
        UniqueConstraint("mailbox_id", "label_id", name="uq_category_label_label"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    label_id: Mapped[str] = mapped_column(String(64))
    label_name: Mapped[str] = mapped_column(Text)


class Filing(Base):
    """Which category a mail was filed under with which list version; no sender and no subject (AC-22)."""

    __tablename__ = "filing"
    __table_args__ = (
        Index("ix_filing_filed_at", "mailbox_id", "filed_at"),
        CheckConstraint("source IN ('model', 'sender_rule', 'sender_rule_not_applied')", name="ck_filing_source"),
        CheckConstraint("char_length(source_ref) <= 320", name="ck_filing_source_ref_length"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    list_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    filed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    # Migrations 0024, 0025 (ADR-0053): topic and extra label, how the mail was filed, the sender entry that matched.
    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    extra_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    source: Mapped[str] = mapped_column(String(24), server_default="model")
    source_ref: Mapped[str | None] = mapped_column(Text)


class ListCursor(Base):
    """The last list version whose Gmail effects are done; advanced only after them."""

    __tablename__ = "list_cursor"
    __table_args__ = (CheckConstraint("last_version >= 0", name="ck_list_cursor_positive"), {"schema": "categories"})

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    last_version: Mapped[int] = mapped_column(Integer)
    advanced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Rejection(Base):
    """A mail the user left out of a plan; kept until the list changes again."""

    __tablename__ = "rejection"
    __table_args__ = ({"schema": "categories"},)

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    list_version: Mapped[int] = mapped_column(Integer)
    rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class TelegramAction(Base):
    """A button of a Telegram message: only the hash of its nonce, single use by compare-and-set."""

    __tablename__ = "telegram_action"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('undo', 'lock', 'plan_cancel', 'plan_lock', 'plan_move_back')", name="ck_telegram_action_kind"
        ),
        Index("ix_telegram_action_expires_at", "mailbox_id", "expires_at"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    nonce_hash: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplyConfig(Base):
    """The apply threshold and delay of a mailbox; only the agent writes it, from its deployment configuration."""

    __tablename__ = "apply_config"
    __table_args__ = (
        CheckConstraint("threshold >= 1", name="ck_apply_config_threshold"),
        CheckConstraint("delay_minutes >= 0", name="ck_apply_config_delay"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    threshold: Mapped[int] = mapped_column(Integer)
    delay_minutes: Mapped[int] = mapped_column(Integer)


# --- Mail categories, plan half (INT-004, ADR-0046, ADR-0047): migration 0015 -----------------------------------------


class ResortRequest(Base):
    """Insert-only "Sort everything again" request (0029); written by ``request_resort`` alone."""

    __tablename__ = "resort_request"
    __table_args__ = (
        CheckConstraint("threshold BETWEEN 50 AND 100", name="ck_resort_request_threshold"),
        CheckConstraint("channel IN ('telegram', 'web', 'operator')", name="ck_resort_request_channel"),
        Index("ix_resort_request_at", "mailbox_id", "at"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    threshold: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(16), server_default="operator")
    actor_digest: Mapped[str] = mapped_column(CHAR(64), server_default=text("repeat('0', 64)"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Plan(Base):
    """One re-sort plan; its state moves follow ``app.core.resort_plan`` (a trigger refuses the others)."""

    __tablename__ = "plan"
    __table_args__ = (
        CheckConstraint(
            "state IN ('building', 'ready', 'scheduled', 'applying', 'applied', 'replaced', 'discarded', 'cancelled')",
            name="ck_plan_state",
        ),
        CheckConstraint("checked_count >= 0 AND cap >= 1 AND unclear_count >= 0", name="ck_plan_counts"),
        CheckConstraint(
            "(estimate_total IS NULL OR estimate_total >= 0) AND not_looked_at >= 0", name="ck_plan_progress"
        ),
        CheckConstraint("moved_count >= 0", name="ck_plan_moved_count"),
        CheckConstraint("kind IN ('auto', 'review')", name="ck_plan_kind"),
        CheckConstraint(
            "kind = 'review' OR (request_id IS NOT NULL AND threshold IS NOT NULL)", name="ck_plan_request"
        ),
        CheckConstraint("threshold IS NULL OR threshold BETWEEN 50 AND 100", name="ck_plan_threshold"),
        ForeignKeyConstraint(
            ["mailbox_id", "request_id"],
            ["categories.resort_request.mailbox_id", "categories.resort_request.id"],
            name="fk_plan_request",
        ),
        Index(
            "uq_plan_one_open",
            "mailbox_id",
            "kind",
            unique=True,
            postgresql_where=text("state NOT IN ('applied', 'replaced', 'discarded', 'cancelled')"),
        ),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    list_version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), server_default="building")
    apply_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    build_cursor: Mapped[str | None] = mapped_column(Text)
    checked_count: Mapped[int] = mapped_column(Integer, server_default="0")
    cap: Mapped[int] = mapped_column(Integer, server_default="5000")
    unclear_count: Mapped[int] = mapped_column(Integer, server_default="0")
    estimate_total: Mapped[int | None] = mapped_column(Integer)  # estimated mails in scope: "N of about M" (0016)
    not_looked_at: Mapped[int] = mapped_column(Integer, server_default="0")  # in scope but past the cap (D15, 0016)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    apply_run_id: Mapped[str | None] = mapped_column(String(64))  # the run that holds an applying plan (0018)
    apply_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # notice of a delayed plan (0018)
    moved_count: Mapped[int] = mapped_column(Integer, server_default="0")  # items moved; the items go (0022)
    kind: Mapped[str] = mapped_column(String(8), server_default="review")  # auto or review (0029)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # the sort-again request of the plan (0029)
    threshold: Mapped[int | None] = mapped_column(Integer)  # copied from the request, never changes (0029)


class PlanItem(Base):
    """One planned move. The decision changes only through ``record_decision`` and ``approve_plan``."""

    __tablename__ = "plan_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mailbox_id", "plan_id"], ["categories.plan.mailbox_id", "categories.plan.id"], name="fk_plan_item_plan"
        ),
        UniqueConstraint("mailbox_id", "plan_id", "message_id", name="uq_plan_item_message"),
        CheckConstraint("char_length(subject) <= 120", name="ck_plan_item_subject"),
        CheckConstraint("decision IN ('pending', 'approved', 'rejected')", name="ck_plan_item_decision"),
        CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'applied', 'skipped', 'failed')", name="ck_plan_item_state"
        ),
        CheckConstraint(
            "state NOT IN ('applied', 'skipped', 'failed') OR decision = 'approved'", name="ck_plan_item_applied"
        ),
        CheckConstraint("state NOT IN ('approved', 'rejected') OR state = decision", name="ck_plan_item_decided"),
        CheckConstraint("confidence_pct IS NULL OR confidence_pct BETWEEN 0 AND 100", name="ck_plan_item_confidence"),
        CheckConstraint("decision_source IN ('user', 'threshold')", name="ck_plan_item_decision_source"),
        CheckConstraint(
            "decision_source <> 'threshold' OR decision = 'approved'", name="ck_plan_item_threshold_approved"
        ),
        CheckConstraint("char_length(tip) <= 500", name="ck_plan_item_tip"),
        Index("ix_plan_item_group", "mailbox_id", "plan_id", "old_category_id", "new_category_id"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64))
    sender_name: Mapped[str] = mapped_column(Text)
    sender_address: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    old_category_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    new_category_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    decision: Mapped[str] = mapped_column(String(16), server_default="pending")
    state: Mapped[str] = mapped_column(String(16), server_default="pending")
    reason: Mapped[str | None] = mapped_column(String(64))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")  # failed moves of this item (0018)
    old_topic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # the pair before and after (0029)
    old_extra_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    new_topic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    new_extra_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    confidence_pct: Mapped[int | None] = mapped_column(Integer)  # the model's own report, 0 to 100 (0029)
    decision_source: Mapped[str] = mapped_column(String(16), server_default="user")  # user or threshold (0029)
    tip: Mapped[str | None] = mapped_column(Text)  # plain text, at most 500 characters (0029)


class PlanDecision(Base):
    """Append-only record of a decision call; channel and actor are derived from the session role."""

    __tablename__ = "plan_decision"
    __table_args__ = (
        CheckConstraint("scope IN ('group', 'ids', 'all')", name="ck_plan_decision_scope"),
        CheckConstraint("channel IN ('telegram', 'web', 'operator')", name="ck_plan_decision_channel"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    scope: Mapped[str] = mapped_column(String(8))
    item_count: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    actor_digest: Mapped[str] = mapped_column(CHAR(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class PlanApproval(Base):
    """Append-only record of an approval; the rolling 24 hours threshold counts ``approved_count``."""

    __tablename__ = "plan_approval"
    __table_args__ = (
        CheckConstraint("approved_count >= 0", name="ck_plan_approval_count"),
        CheckConstraint("channel IN ('telegram', 'web', 'operator', 'system')", name="ck_plan_approval_channel"),
        Index("ix_plan_approval_at", "mailbox_id", "at"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    approved_count: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(16))
    actor_digest: Mapped[str] = mapped_column(CHAR(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class ApplyAudit(Base):
    """One label move of an apply or a move back: message id and labels only, no sender and no subject."""

    __tablename__ = "apply_audit"
    __table_args__ = (
        CheckConstraint("channel IN ('telegram', 'web', 'operator', 'system')", name="ck_apply_audit_channel"),
        CheckConstraint("kind IN ('apply', 'restore')", name="ck_apply_audit_kind"),
        Index("ix_apply_audit_plan", "mailbox_id", "plan_id"),
        Index(
            "uq_apply_audit_intent",
            "mailbox_id",
            "plan_id",
            "message_id",
            unique=True,
            postgresql_where=text("kind = 'apply'"),
        ),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    message_id: Mapped[str] = mapped_column(String(64))
    old_label: Mapped[str] = mapped_column(Text)
    new_label: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(16))
    actor_digest: Mapped[str] = mapped_column(CHAR(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    kind: Mapped[str] = mapped_column(String(8), server_default="apply")  # "restore" for a row of a move back (0018)


class MoveBackRequest(Base):
    """The user asked to restore the labels of an applied plan; the agent processes it once."""

    __tablename__ = "move_back_request"
    __table_args__ = ({"schema": "categories"},)

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    processed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    actor_digest: Mapped[str] = mapped_column(CHAR(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    run_id: Mapped[str | None] = mapped_column(String(64))  # the run that processes the request (0018)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefileReport(Base):
    """One daily run of the re-file report: counts only, no sender, subject or message id (AC-30, 0019).

    The agent role has no right on this table; it appends through ``categories.record_refile_report``.
    """

    __tablename__ = "refile_report"
    __table_args__ = (
        CheckConstraint(
            "filed >= 0 AND checked >= 0 AND refiled >= 0 AND in_other >= 0 AND gone >= 0 "
            "AND checked <= filed AND refiled <= checked AND in_other <= checked AND gone <= checked",
            name="ck_refile_report_counts",
        ),
        Index("ix_refile_report_at", "mailbox_id", "at"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    filed: Mapped[int] = mapped_column(Integer)
    checked: Mapped[int] = mapped_column(Integer)
    refiled: Mapped[int] = mapped_column(Integer)
    in_other: Mapped[int] = mapped_column(Integer)
    gone: Mapped[int] = mapped_column(Integer)


# --- Category contract v2 (INT-008, ADR-0053, ADR-0058): migration 0024 ---------------------------------------------


class CategorySender(Base):
    """A sender entry of a category in one list version. Insert-only, like ``category``."""

    __tablename__ = "category_sender"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mailbox_id", "version", "category_id"],
            ["categories.category.mailbox_id", "categories.category.version", "categories.category.id"],
            name="fk_category_sender_category",
        ),
        CheckConstraint("char_length(entry) BETWEEN 1 AND 320", name="ck_category_sender_entry_length"),
        CheckConstraint("is_domain OR NOT subdomains", name="ck_category_sender_subdomains"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    entry: Mapped[str] = mapped_column(Text, primary_key=True)
    is_domain: Mapped[bool] = mapped_column(Boolean)
    subdomains: Mapped[bool] = mapped_column(Boolean, server_default=false())


class ListSettings(Base):
    """The list-level fields of one list version: the general instructions and the archive label name."""

    __tablename__ = "list_settings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mailbox_id", "version"],
            ["categories.list_version.mailbox_id", "categories.list_version.version"],
            name="fk_list_settings_list_version",
        ),
        CheckConstraint("char_length(general_instructions) <= 4000", name="ck_list_settings_instructions"),
        CheckConstraint("char_length(archive_label) BETWEEN 1 AND 255", name="ck_list_settings_archive_label"),
        CheckConstraint("char_length(other_label) BETWEEN 1 AND 255", name="ck_list_settings_other_label"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    general_instructions: Mapped[str] = mapped_column(Text, server_default="")
    archive_label: Mapped[str] = mapped_column(Text, server_default="Archive")  # rows from before 0030 keep their value
    other_label: Mapped[str] = mapped_column(Text, server_default="Other")  # 0030


class UploadPreview(Base):
    """The preview of a YAML upload: bound to a session, a file hash and a list version; written by the api only."""

    __tablename__ = "upload_preview"
    __table_args__ = (
        CheckConstraint("base_version >= 0", name="ck_upload_preview_base_version"),
        Index("ix_upload_preview_expires_at", "expires_at"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_digest: Mapped[str] = mapped_column(CHAR(64))
    file_hash: Mapped[str] = mapped_column(CHAR(64))
    base_version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- The label boundary (INT-010, ADR-0060, ADR-0061): migration 0030 -----


class ManagedLabel(Base):
    """A Gmail label the agent may change, by id: a category of the list, "other" or the archive label."""

    __tablename__ = "managed_label"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "category_id", name="uq_managed_label_category"),
        ForeignKeyConstraint(
            ["mailbox_id", "category_id"],
            ["categories.category_identity.mailbox_id", "categories.category_identity.id"],
            name="fk_managed_label_identity",
        ),
        CheckConstraint("role IN ('category', 'other', 'archive')", name="ck_managed_label_role"),
        CheckConstraint("(role = 'category') = (category_id IS NOT NULL)", name="ck_managed_label_category"),
        CheckConstraint("char_length(label_name) <= 255", name="ck_managed_label_name_length"),
        Index("uq_managed_label_role", "mailbox_id", "role", unique=True, postgresql_where=text("role <> 'category'")),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    label_id: Mapped[str] = mapped_column(Text, primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    label_name: Mapped[str] = mapped_column(Text)


class LabelMigration(Base):
    """The per-mailbox state of the one-off rename (``pending``, ``confirmed``, ``done``); it gates label writes."""

    __tablename__ = "label_migration"
    __table_args__ = (
        CheckConstraint("state IN ('pending', 'confirmed', 'done')", name="ck_label_migration_state"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(12))
    plan_hash: Mapped[str | None] = mapped_column(CHAR(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class LabelRenameItem(Base):
    """One label of the rename plan, and the backup of its old name."""

    __tablename__ = "label_rename_item"
    __table_args__ = (
        CheckConstraint("action IN ('rename', 'merge')", name="ck_label_rename_item_action"),
        CheckConstraint("state IN ('planned', 'skipped', 'done', 'kept')", name="ck_label_rename_item_state"),
        CheckConstraint("mail_count >= 0", name="ck_label_rename_item_count"),
        CheckConstraint("char_length(old_name) <= 255", name="ck_label_rename_item_old_name_length"),
        CheckConstraint("char_length(new_name) <= 255", name="ck_label_rename_item_new_name_length"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    label_id: Mapped[str] = mapped_column(Text, primary_key=True)
    old_name: Mapped[str] = mapped_column(Text)
    new_name: Mapped[str] = mapped_column(Text)
    mail_count: Mapped[int] = mapped_column(Integer, server_default="0")
    action: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(8), server_default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class LabelEmptySince(Base):
    """The persistent timer of the delayed delete, per label id."""

    __tablename__ = "label_empty_since"
    __table_args__ = (
        CheckConstraint("last_seen_empty >= empty_since", name="ck_label_empty_since_order"),
        CheckConstraint("wait_minutes BETWEEN 5 AND 720", name="ck_label_empty_since_wait"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    label_id: Mapped[str] = mapped_column(Text, primary_key=True)
    empty_since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_empty: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    wait_minutes: Mapped[int] = mapped_column(SmallInteger)  # the waiting time the timer started with (R3)


class DeletedLabel(Base):
    """A label the agent deleted: the hash of its id and its name, shown as "recently deleted" for the retention."""

    __tablename__ = "deleted_label"
    __table_args__ = (
        CheckConstraint("label_id_hash ~ '^[0-9a-f]{64}$'", name="ck_deleted_label_hash"),
        CheckConstraint("char_length(name) <= 255", name="ck_deleted_label_name_length"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    label_id_hash: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class LabelConfirmation(Base):
    """Insert-only confirmation of the rename plan; written by ``confirm_label_rename`` alone."""

    __tablename__ = "label_confirmation"
    __table_args__ = (
        UniqueConstraint("mailbox_id", name="uq_label_confirmation_mailbox"),
        CheckConstraint("channel IN ('telegram', 'web', 'operator')", name="ck_label_confirmation_channel"),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    plan_hash: Mapped[str] = mapped_column(CHAR(64))
    skipped_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    channel: Mapped[str] = mapped_column(String(16), server_default="operator")
    actor_digest: Mapped[str] = mapped_column(CHAR(64), server_default=text("repeat('0', 64)"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class LabelRestoreRequest(Base):
    """Insert-only request to give the old label names back; written by ``request_label_restore`` alone."""

    __tablename__ = "label_restore_request"
    __table_args__ = (
        CheckConstraint("channel IN ('telegram', 'web', 'operator')", name="ck_label_restore_request_channel"),
        Index(
            "uq_label_restore_request_open", "mailbox_id", unique=True, postgresql_where=text("processed_at IS NULL")
        ),
        {"schema": "categories"},
    )

    mailbox_id: Mapped[str] = mapped_column(ForeignKey("categories.mailbox.id"), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    channel: Mapped[str] = mapped_column(String(16), server_default="operator")
    actor_digest: Mapped[str] = mapped_column(CHAR(64), server_default=text("repeat('0', 64)"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
