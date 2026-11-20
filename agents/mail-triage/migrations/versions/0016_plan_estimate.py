"""Plan build progress for the review page (INT-004, U-mail-categories-14, ADR-0046).

``plan.estimate_total`` is the estimated number of mails in scope ("N of about M checked") and ``plan.not_looked_at``
the mails past the cap (D15). Both are written by the agent while it builds; the api only reads them. The rights on
``plan`` are table-wide (``app/db/grants.sql``), so nothing is granted here.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the two counts."""
    op.add_column("plan", sa.Column("estimate_total", sa.Integer), schema="categories")
    op.add_column(
        "plan", sa.Column("not_looked_at", sa.Integer, nullable=False, server_default="0"), schema="categories"
    )
    op.create_check_constraint(
        "ck_plan_progress",
        "plan",
        "(estimate_total IS NULL OR estimate_total >= 0) AND not_looked_at >= 0",
        schema="categories",
    )


def downgrade() -> None:
    """Remove the two counts."""
    op.drop_constraint("ck_plan_progress", "plan", schema="categories")
    op.drop_column("plan", "not_looked_at", schema="categories")
    op.drop_column("plan", "estimate_total", schema="categories")
