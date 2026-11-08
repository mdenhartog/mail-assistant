"""Initial tables of the mail-triage agent.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    """Create all tables."""
    op.create_table(
        "mail_item",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("gmail_message_id", sa.String(64), nullable=False, unique=True),
        sa.Column("thread_id", sa.String(64), nullable=False),
        sa.Column("label", sa.String(80)),
        sa.Column("urgent", sa.Boolean, nullable=False),
        sa.Column("confidence", sa.Float),
        sa.Column("created_at", _TZ, nullable=False),
    )
    op.create_table(
        "alert",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("mail_item_id", sa.Integer, sa.ForeignKey("mail_item.id"), nullable=False, unique=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("due_at", _TZ),
        sa.Column("telegram_message_id", sa.BigInteger),
        sa.Column("created_at", _TZ, nullable=False),
        sa.Column("updated_at", _TZ, nullable=False),
    )
    op.create_table(
        "draft",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.Integer, sa.ForeignKey("alert.id")),
        sa.Column("recipient", sa.String(320)),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("expires_at", _TZ, nullable=False),
        sa.Column("used", sa.Boolean, nullable=False),
        sa.Column("created_at", _TZ, nullable=False),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", _TZ, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("mail_item_id", sa.Integer),
        sa.Column("ref", sa.String(64)),
        sa.Column("digest", sa.String(64)),
        sa.Column("detail", sa.String(200)),
    )
    op.create_table(
        "oauth_token",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("updated_at", _TZ, nullable=False),
    )
    op.create_table(
        "poll_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("history_id", sa.String(32)),
    )


def downgrade() -> None:
    """Drop all tables."""
    for table in ("poll_state", "oauth_token", "audit_log", "draft", "alert", "mail_item"):
        op.drop_table(table)
