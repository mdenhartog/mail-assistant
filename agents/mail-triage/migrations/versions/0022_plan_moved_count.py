"""The plan keeps how many mails its apply moved (INT-004, U-mail-categories-32, AC-39, C-18).

``remove_applied_items`` deletes the items an apply moved at once, so "310 moved" cannot be counted from the items
later. ``plan.moved_count`` holds the number; only the definer function writes it (the agent role has no UPDATE right on
the column, so it cannot forge it) and it adds what it removes, so a repeated call keeps the number.

Revision ID: 0022
Revises: 0021
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_SCHEMA = "categories"

_REMOVE_APPLIED = """
CREATE OR REPLACE FUNCTION categories.remove_applied_items(p_mailbox text, p_plan uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_removed integer;
BEGIN
    DELETE FROM categories.plan_item i
     WHERE i.mailbox_id = p_mailbox AND i.plan_id = p_plan AND i.state = 'applied'
       AND EXISTS (SELECT 1 FROM categories.plan p
                    WHERE p.mailbox_id = p_mailbox AND p.id = p_plan AND p.state = 'applied');
    GET DIAGNOSTICS v_removed = ROW_COUNT;
    IF v_removed > 0 THEN
        UPDATE categories.plan p SET moved_count = p.moved_count + v_removed
         WHERE p.mailbox_id = p_mailbox AND p.id = p_plan;
    END IF;
    RETURN v_removed;
END
$$
"""


def _function_before() -> str:
    """The function of revision 0018, read from that revision: one copy of the text."""
    path = Path(__file__).with_name("0018_plan_apply_runtime.py")
    spec = importlib.util.spec_from_file_location("categories_0018", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("revision 0018 cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module._REMOVE_APPLIED).replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


def upgrade() -> None:
    """Add the counter and let the removal of the moved items add to it."""
    op.add_column("plan", sa.Column("moved_count", sa.Integer, nullable=False, server_default="0"), schema=_SCHEMA)
    op.create_check_constraint("ck_plan_moved_count", "plan", "moved_count >= 0", schema=_SCHEMA)
    op.execute(_REMOVE_APPLIED)


def downgrade() -> None:
    """Restore the function of revision 0018 and drop the counter."""
    op.execute(_function_before())
    op.drop_constraint("ck_plan_moved_count", "plan", schema=_SCHEMA)
    op.drop_column("plan", "moved_count", schema=_SCHEMA)
