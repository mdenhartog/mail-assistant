"""Undo burst id (INT-002, ADR-0033, CR-07): each Undo token record names its burst and the burst's first version.

Upgrade: ``web_notice_token`` gains ``burst_id`` (text) and ``first_version`` (int), both NOT NULL. Records that exist
at upgrade time are grouped as the old guard grouped them (equal ``before``): they share one id, derived from the
``before`` text, and the lowest version of the group. The records live 24 hours, so this only keeps the notices that
are still open working.
The agent role's table-level grant (``app/db/grants.sql``) already covers the new columns; no grant changes.

Downgrade: both columns go. Token records stay.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"  # 0008 is the head on main
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the columns, fill them for the records that exist, then require them."""
    op.add_column("web_notice_token", sa.Column("burst_id", sa.String(64), nullable=True))
    op.add_column("web_notice_token", sa.Column("first_version", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE web_notice_token AS t
        SET burst_id = g.burst_id, first_version = g.first_version
        FROM (
            SELECT before, md5(before::text) AS burst_id, min(version) AS first_version
            FROM web_notice_token
            GROUP BY before
        ) AS g
        WHERE t.before = g.before
        """
    )
    op.alter_column("web_notice_token", "burst_id", nullable=False)
    op.alter_column("web_notice_token", "first_version", nullable=False)
    op.create_index("ix_web_notice_token_burst_id", "web_notice_token", ["burst_id"])


def downgrade() -> None:
    """Drop the columns."""
    op.drop_index("ix_web_notice_token_burst_id", table_name="web_notice_token")
    op.drop_column("web_notice_token", "first_version")
    op.drop_column("web_notice_token", "burst_id")
