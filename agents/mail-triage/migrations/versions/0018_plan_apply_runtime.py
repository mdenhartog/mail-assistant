"""What the agent needs to run the plan build and apply for real (INT-004, U-mail-categories-22).

- ``plan.apply_run_id`` and ``plan.apply_lease_until``: the run that holds an ``applying`` plan, and until when. A
  crashed run's lease ends and another run takes over; two runs never work on one plan.
- ``move_back_request.run_id`` and ``lease_until``: the same for a move-back request.
- ``plan_item.attempts``: how often a move failed; after a limit the item ends ``failed`` and no longer blocks the plan.
- ``apply_audit.kind``: ``apply`` or ``restore``. A move back writes its restore rows under the plan of the apply; it
  reads the ``apply`` rows only. At most one ``apply`` row exists per plan and mail (the intent is written once).
- ``categories.replace_plan`` and ``categories.remove_applied_items`` (SECURITY DEFINER, owned by the non-login
  ``categories_definer``): the agent role has no DELETE right on ``plan_item`` (ADR-0047), yet a replaced plan drops its
  items and an applied plan drops the items it moved. Both fix their own state test and take only a mailbox and a plan.

Rights are in ``app/db/grants.sql``; nothing is granted here.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_SCHEMA = "categories"
_TZ = sa.DateTime(timezone=True)

# A plan that is still building or ready becomes replaced and its items go, in one statement sequence under the row
# lock of the update: a concurrent progress write waits for it and then finds a plan that is no longer building.
_REPLACE_PLAN = """
CREATE FUNCTION categories.replace_plan(p_mailbox text, p_plan uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    UPDATE categories.plan p SET state = 'replaced', last_activity_at = now()
     WHERE p.mailbox_id = p_mailbox AND p.id = p_plan AND p.state IN ('building', 'ready');
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    DELETE FROM categories.plan_item i WHERE i.mailbox_id = p_mailbox AND i.plan_id = p_plan;
    RETURN true;
END
$$
"""

# The items the apply moved go at once (spec AC-39); the ones it skipped stay for the page until the retention purge.
_REMOVE_APPLIED = """
CREATE FUNCTION categories.remove_applied_items(p_mailbox text, p_plan uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_removed integer;
BEGIN
    DELETE FROM categories.plan_item i
     WHERE i.mailbox_id = p_mailbox AND i.plan_id = p_plan AND i.state = 'applied'
       AND EXISTS (SELECT 1 FROM categories.plan p
                    WHERE p.mailbox_id = p_mailbox AND p.id = p_plan AND p.state = 'applied');
    GET DIAGNOSTICS v_removed = ROW_COUNT;
    RETURN v_removed;
END
$$
"""

_FUNCTIONS = ("categories.replace_plan(text, uuid)", "categories.remove_applied_items(text, uuid)")


def upgrade() -> None:
    """Add the leases, the attempt counter, the audit kind and the two functions."""
    op.add_column("plan", sa.Column("apply_run_id", sa.String(64)), schema=_SCHEMA)
    op.add_column("plan", sa.Column("apply_lease_until", _TZ), schema=_SCHEMA)
    op.add_column("plan_item", sa.Column("attempts", sa.Integer, nullable=False, server_default="0"), schema=_SCHEMA)
    op.create_check_constraint("ck_plan_item_attempts", "plan_item", "attempts >= 0", schema=_SCHEMA)
    op.add_column("move_back_request", sa.Column("run_id", sa.String(64)), schema=_SCHEMA)
    op.add_column("move_back_request", sa.Column("lease_until", _TZ), schema=_SCHEMA)
    op.add_column(
        "apply_audit", sa.Column("kind", sa.String(8), nullable=False, server_default="apply"), schema=_SCHEMA
    )
    op.create_check_constraint("ck_apply_audit_kind", "apply_audit", "kind IN ('apply', 'restore')", schema=_SCHEMA)
    op.create_index(
        "uq_apply_audit_intent",
        "apply_audit",
        ["mailbox_id", "plan_id", "message_id"],
        unique=True,
        schema=_SCHEMA,
        postgresql_where=sa.text("kind = 'apply'"),
    )
    for function_sql in (_REPLACE_PLAN, _REMOVE_APPLIED):
        op.execute(function_sql)
    for function in _FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
        op.execute(f"ALTER FUNCTION {function} OWNER TO categories_definer")


def downgrade() -> None:
    """Remove what upgrade made."""
    for function in _FUNCTIONS:
        op.execute(f"DROP FUNCTION {function}")
    op.drop_index("uq_apply_audit_intent", table_name="apply_audit", schema=_SCHEMA)
    op.drop_constraint("ck_apply_audit_kind", "apply_audit", schema=_SCHEMA)
    op.drop_column("apply_audit", "kind", schema=_SCHEMA)
    op.drop_column("move_back_request", "lease_until", schema=_SCHEMA)
    op.drop_column("move_back_request", "run_id", schema=_SCHEMA)
    op.drop_constraint("ck_plan_item_attempts", "plan_item", schema=_SCHEMA)
    op.drop_column("plan_item", "attempts", schema=_SCHEMA)
    op.drop_column("plan", "apply_lease_until", schema=_SCHEMA)
    op.drop_column("plan", "apply_run_id", schema=_SCHEMA)
