"""Settings guard: the database enforces the version step and derives the channel and the actor of a change (ADR-0030).

Upgrade: a ``BEFORE INSERT OR UPDATE`` trigger on ``settings.schedule`` (owned by the owner role, like the table)
- refuses a first row above version 1 and an update that does not raise the version by exactly one,
- refuses a write whose ``updated_via`` is not the channel of the session role (``mail_triage_runtime`` means
  ``telegram``; add the web backend role to ``settings.schedule_guard`` when it exists), and
- sets ``updated_at`` to the server clock.
A session role that is not mapped (the owner role, an operator) keeps the channel it claims. The audit trigger now also
stores ``session_user`` in the new column ``settings_change.db_role``; records written before this revision get
``unknown``. Existing rows stay valid.

Downgrade: the guard and the column go; the audit function returns to its 0004 form.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Refusals use 42501 (insufficient_privilege), the same SQLSTATE as a denied grant: the write is not allowed.
_GUARD = """
CREATE FUNCTION settings.schedule_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    channel text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.version IS DISTINCT FROM OLD.version + 1 THEN
            RAISE EXCEPTION 'settings version must rise by exactly one' USING ERRCODE = '42501';
        END IF;
    ELSIF NEW.version IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'the first settings row must have version 1' USING ERRCODE = '42501';
    END IF;
    -- The channel follows the database login, not the writer's claim. One line per login role that may write.
    channel := CASE session_user
        WHEN 'mail_triage_runtime' THEN 'telegram'
    END;
    IF channel IS NOT NULL AND NEW.updated_via IS DISTINCT FROM channel THEN
        RAISE EXCEPTION 'this database role may only write as %', channel USING ERRCODE = '42501';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END
$$
"""

# SECURITY DEFINER with a pinned search_path, as in 0004; session_user is not changed by SECURITY DEFINER.
_AUDIT_WITH_ROLE = """
CREATE OR REPLACE FUNCTION settings.settings_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    INSERT INTO settings.settings_change (at, via, by, db_role, old, new)
    VALUES (
        now(), NEW.updated_via, NEW.updated_by, session_user::varchar,
        CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(OLD) END, to_jsonb(NEW)
    );
    RETURN NULL;
END
$$
"""

_AUDIT_0004 = """
CREATE OR REPLACE FUNCTION settings.settings_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    INSERT INTO settings.settings_change (at, via, by, old, new)
    VALUES (
        now(), NEW.updated_via, NEW.updated_by,
        CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(OLD) END, to_jsonb(NEW)
    );
    RETURN NULL;
END
$$
"""


def upgrade() -> None:
    """Add the actor column, record it in the audit function and install the guard."""
    op.add_column("settings_change", sa.Column("db_role", sa.String(63)), schema="settings")
    op.execute("UPDATE settings.settings_change SET db_role = 'unknown'")
    op.alter_column("settings_change", "db_role", nullable=False, schema="settings")
    op.execute(_AUDIT_WITH_ROLE)
    op.execute(_GUARD)
    op.execute("REVOKE ALL ON FUNCTION settings.schedule_guard() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER schedule_guard BEFORE INSERT OR UPDATE ON settings.schedule "
        "FOR EACH ROW EXECUTE FUNCTION settings.schedule_guard()"
    )


def downgrade() -> None:
    """Remove the guard and the column; the audit function is the one of 0004 again."""
    op.execute("DROP TRIGGER schedule_guard ON settings.schedule")
    op.execute("DROP FUNCTION settings.schedule_guard()")
    op.execute(_AUDIT_0004)
    op.drop_column("settings_change", "db_role", schema="settings")
