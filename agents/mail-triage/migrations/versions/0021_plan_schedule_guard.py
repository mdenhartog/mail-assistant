"""Only ``approve_plan`` schedules a plan or sets ``apply_after`` (INT-004, U-mail-categories-26, RED-006, ADR-0046).

The agent role wrote ``categories.plan`` table-wide, so it could move ``ready`` to ``scheduled`` and lower
``apply_after`` without the approval, the threshold and the delay. ``grants.sql`` now limits the agent to the columns it
writes (no ``apply_after``, no ``list_version``, and it can only insert a ``building`` plan). This revision adds the
second line, in the database:

- ``plan_state_guard`` also refuses ``ready`` to ``scheduled`` for every role that is not a member of the definer role
  that owns ``approve_plan`` (the owner of the database is, as a superuser); the refusal is SQLSTATE 42501.
- ``plan_apply_after_guard`` refuses any change of ``apply_after`` by such a role, with the same SQLSTATE.

Revision ID: 0021
Revises: 0020
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_MEMBER = "pg_catalog.pg_has_role(current_user, 'categories_definer', 'USAGE')"

_STATE_GUARD = f"""
CREATE OR REPLACE FUNCTION categories.plan_state_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF (OLD.state, NEW.state) NOT IN (
        ('building', 'ready'), ('building', 'replaced'),
        ('ready', 'replaced'), ('ready', 'scheduled'), ('ready', 'discarded'),
        ('scheduled', 'cancelled'), ('scheduled', 'applying'),
        ('applying', 'cancelled'), ('applying', 'applied')) THEN
        RAISE EXCEPTION 'this plan state move is not allowed' USING ERRCODE = 'MC409';
    END IF;
    IF NEW.state = 'scheduled' AND NOT {_MEMBER} THEN
        RAISE EXCEPTION 'only the approval schedules a plan' USING ERRCODE = '42501';
    END IF;
    IF NEW.state IN ('applied', 'replaced', 'discarded', 'cancelled') THEN
        NEW.terminal_at := now();
    END IF;
    RETURN NEW;
END
$$
"""

_APPLY_AFTER_GUARD = f"""
CREATE FUNCTION categories.plan_apply_after_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NOT {_MEMBER} THEN
        RAISE EXCEPTION 'only the approval sets when a plan starts' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END
$$
"""

_TRIGGER = (
    "CREATE TRIGGER plan_apply_after_guard BEFORE UPDATE OF apply_after ON categories.plan "
    "FOR EACH ROW WHEN (OLD.apply_after IS DISTINCT FROM NEW.apply_after) "
    "EXECUTE FUNCTION categories.plan_apply_after_guard()"
)


def _state_guard_before() -> str:
    """The guard of revision 0015, read from that revision: one copy of the text."""
    path = Path(__file__).with_name("0015_categories_plan.py")
    spec = importlib.util.spec_from_file_location("categories_0015", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("revision 0015 cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module._PLAN_GUARD).replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


def upgrade() -> None:
    """Refuse the scheduling and the change of ``apply_after`` for every role but the definer."""
    op.execute(_STATE_GUARD)
    op.execute(_APPLY_AFTER_GUARD)
    op.execute(_TRIGGER)


def downgrade() -> None:
    """Restore the guard of revision 0015 and drop the second one."""
    op.execute("DROP TRIGGER plan_apply_after_guard ON categories.plan")
    op.execute("DROP FUNCTION categories.plan_apply_after_guard()")
    op.execute(_state_guard_before())
