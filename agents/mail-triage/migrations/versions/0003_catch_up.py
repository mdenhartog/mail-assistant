"""One-time catch-up of the unread inbox mail (INT-003, ADR-0021).

Adds the single-row ``catchup_state`` (when the catch-up started and when it finished) and flags the mails the catch-up
filed, so its alerts can be counted.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    """Create the state table and the backlog flag."""
    op.create_table(
        "catchup_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("started_at", _TZ, nullable=False),
        sa.Column("finished_at", _TZ),
        sa.CheckConstraint("id = 1", name="ck_catchup_state_single_row"),
    )
    op.add_column("mail_item", sa.Column("backlog", sa.Boolean, nullable=False, server_default="false"))


def downgrade() -> None:
    """Remove them again; the mail itself stays."""
    op.drop_column("mail_item", "backlog")
    op.drop_table("catchup_state")
