"""The always-notify alert keeps its causes and the sender check (INT-008, U-label-structure-10, ADR-0057).

``alert.causes`` lists why the alert exists (``urgent``, ``always_notify:<category>``), so one alert names every cause
also after a restart; ``alert.by_rule`` marks a mail a sender rule filed (no summary in its alert);
``mail_item.verified_domain`` is the From domain Gmail vouches for (ADR-0054), replacing the weaker ``auth_*`` parse.
The ``auth_*`` columns stay for the previous release during a rollout and are no longer written; a later revision drops
them. Rights are in ``app/db/grants.sql``; the tables are already granted.

Revision ID: 0026
Revises: 0025
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the three columns; every existing alert reads as an urgent one (causes ``NULL``)."""
    op.add_column("alert", sa.Column("causes", JSONB))
    op.add_column("alert", sa.Column("by_rule", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("mail_item", sa.Column("verified_domain", sa.String(255)))


def downgrade() -> None:
    """Remove them again; the alerts and mail stay."""
    op.drop_column("mail_item", "verified_domain")
    op.drop_column("alert", "by_rule")
    op.drop_column("alert", "causes")
