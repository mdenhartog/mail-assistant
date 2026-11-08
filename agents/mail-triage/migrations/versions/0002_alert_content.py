"""Capped alert content, pipeline progress and the overview log (ADR-0020).

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)


def _mail_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("sender", sa.String(320)),
        sa.Column("subject", sa.String(300)),
        sa.Column("reply_to", sa.String(320)),
        sa.Column("reason", sa.String(200)),
        sa.Column("summary", sa.String(400)),
        sa.Column("has_attachment", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("auth_spf", sa.String(16)),
        sa.Column("auth_dkim", sa.String(16)),
        sa.Column("auth_dmarc", sa.String(16)),
        sa.Column("note", sa.String(80)),
        sa.Column("failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("abandoned", sa.Boolean, nullable=False, server_default="false"),
    ]


def upgrade() -> None:
    """Add the columns and the overview log."""
    for column in _mail_columns():
        op.add_column("mail_item", column)
    op.add_column("alert", sa.Column("sent_at", _TZ))
    op.add_column("alert", sa.Column("awaiting_input", sa.String(16)))
    op.create_table(
        "overview_log",
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("settled_at", _TZ, nullable=False),
    )


def downgrade() -> None:
    """Remove them again."""
    op.drop_table("overview_log")
    op.drop_column("alert", "awaiting_input")
    op.drop_column("alert", "sent_at")
    for column in reversed(_mail_columns()):
        op.drop_column("mail_item", column.name)
