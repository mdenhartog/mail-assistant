"""The button kinds of the plan notice (INT-004, U-mail-categories-26, RED-001, ADR-0046).

The constraint of revision 0014 allowed ``undo``, ``cancel``, ``move_back`` and ``lock``, but the notice of a delayed
plan stores ``plan_cancel``, ``plan_lock`` and ``plan_move_back`` (its own kinds, so a button of the list notice can
never be redeemed as a plan button). The constraint now lists the kinds the code uses: ``undo`` and ``lock`` of the
list notice and the three plan kinds. The old ``cancel`` and ``move_back`` were never written by any code.

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_TABLE = "telegram_action"
_NAME = "ck_telegram_action_kind"
_SCHEMA = "categories"
_NEW = "kind IN ('undo', 'lock', 'plan_cancel', 'plan_lock', 'plan_move_back')"
_OLD = "kind IN ('undo', 'cancel', 'move_back', 'lock')"


def upgrade() -> None:
    """Replace the constraint."""
    op.drop_constraint(_NAME, _TABLE, schema=_SCHEMA)
    op.create_check_constraint(_NAME, _TABLE, _NEW, schema=_SCHEMA)


def downgrade() -> None:
    """Restore the old constraint; the plan buttons it would refuse are removed first (they live a day at most)."""
    op.execute("DELETE FROM categories.telegram_action WHERE kind LIKE 'plan\_%'")
    op.drop_constraint(_NAME, _TABLE, schema=_SCHEMA)
    op.create_check_constraint(_NAME, _TABLE, _OLD, schema=_SCHEMA)
