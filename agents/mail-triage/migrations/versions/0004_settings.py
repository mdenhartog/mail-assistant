"""Adjustable quiet hours: the settings schema, the single conversation row and the release moment of held alerts.

Run under the owner role (ADR-0025); the runtime role gets its rights from ``app/db/grants.sql``.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    """Create the schema, its two tables, the conversation row and the column."""
    op.execute("CREATE SCHEMA settings")
    op.create_table(
        "schedule",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("zone", sa.Text, nullable=False),
        sa.Column("quiet_start", sa.SmallInteger, nullable=False),
        sa.Column("quiet_end", sa.SmallInteger, nullable=False),
        sa.Column("overview_at", sa.SmallInteger, nullable=False),
        sa.Column("remind_at", sa.SmallInteger, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_via", sa.String(16), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        schema="settings",
    )
    op.create_table(
        "settings_change",
        sa.Column("at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("via", sa.String(16), nullable=False),
        sa.Column("by", sa.String(64), nullable=False),
        sa.Column("old", postgresql.JSONB),
        sa.Column("new", postgresql.JSONB, nullable=False),
        schema="settings",
    )
    op.create_table(
        "conversation",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("target", sa.String(64)),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("partial", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("expires_at", _TZ, nullable=False),
    )
    op.add_column("alert", sa.Column("release_at", _TZ))


def downgrade() -> None:
    """Remove all of it; ``alert.awaiting_input`` and the mail data stay untouched."""
    op.drop_column("alert", "release_at")
    op.drop_table("conversation")
    op.execute("DROP SCHEMA settings CASCADE")
