"""The list notice cursor (INT-004, U-mail-categories-23, ADR-0033, ADR-0046).

``poll_state.list_notice_version`` is the last category list version Marco was told about in Telegram. It is not the
``categories.list_cursor`` of the label sync (which versions Gmail has seen). The agent's table-wide rights on
``poll_state`` (``app/db/grants.sql``) already cover the new column and the web role has none; nothing is granted here.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the cursor; ``NULL`` means nothing was announced yet."""
    op.add_column("poll_state", sa.Column("list_notice_version", sa.Integer, nullable=True))


def downgrade() -> None:
    """Remove the cursor."""
    op.drop_column("poll_state", "list_notice_version")
