"""The id of the last handled Telegram update (U-quiet-hours-16d, RT-5).

Adds ``poll_state.telegram_update_id``. Without it a restart forgets which update was handled last, Telegram redelivers
the unacknowledged batch, and an old answer could be read as the answer to a new question. The column is empty until the
first update is handled. The runtime role already has INSERT and UPDATE on ``poll_state``; no grant changes.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the column (Telegram update ids can pass 32 bits in principle, so a BIGINT)."""
    op.add_column("poll_state", sa.Column("telegram_update_id", sa.BigInteger))


def downgrade() -> None:
    """Remove it; the Gmail position stays."""
    op.drop_column("poll_state", "telegram_update_id")
