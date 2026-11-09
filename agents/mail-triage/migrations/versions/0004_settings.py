"""Adjustable quiet hours: the settings schema, the single conversation row and the release moment of held alerts.

Run under the owner role (ADR-0025); the runtime role gets its rights from ``app/db/grants.sql``.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)

# Minutes from the quiet start to the quiet end, going forward over midnight when needed.
_LENGTH = "((quiet_end - quiet_start + 1440) % 1440)"


def _outside(column: str) -> str:
    """SQL for "the time is outside the quiet window": start inclusive, end exclusive, midnight-safe."""
    return f"(({column} - quiet_start + 1440) % 1440) >= {_LENGTH}"


def _schedule_checks() -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint("id = 1", name="ck_schedule_single_row"),
        sa.CheckConstraint(
            "quiet_start BETWEEN 0 AND 1439 AND quiet_end BETWEEN 0 AND 1439 "
            "AND overview_at BETWEEN 0 AND 1439 AND remind_at BETWEEN 0 AND 1439",
            name="ck_schedule_minutes_range",
        ),
        sa.CheckConstraint("quiet_start <> quiet_end", name="ck_schedule_quiet_distinct"),
        sa.CheckConstraint(f"{_LENGTH} BETWEEN 60 AND 720", name="ck_schedule_window_length"),
        sa.CheckConstraint(_outside("overview_at"), name="ck_schedule_overview_outside"),
        sa.CheckConstraint(_outside("remind_at"), name="ck_schedule_remind_outside"),
        sa.CheckConstraint("zone ~ '^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$'", name="ck_schedule_zone_pattern"),
        sa.CheckConstraint("updated_via IN ('telegram', 'web')", name="ck_schedule_updated_via"),
    ]


def upgrade() -> None:
    """Create the schema, its two tables, the conversation row and the column."""
    op.execute("CREATE SCHEMA settings")
    op.create_table(
        "schedule",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("zone", sa.Text, nullable=False),
        sa.Column("quiet_start", sa.SmallInteger, nullable=False),
        sa.Column("quiet_end", sa.SmallInteger, nullable=False),
        sa.Column("overview_at", sa.SmallInteger, nullable=False),
        sa.Column("remind_at", sa.SmallInteger, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_via", sa.String(16), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        *_schedule_checks(),
        schema="settings",
    )
    op.create_table(
        "settings_change",
        sa.Column("at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("via", sa.String(16), nullable=False),
        sa.Column("by", sa.String(64), nullable=False),
        sa.Column("old", postgresql.JSONB),
        sa.Column("new", postgresql.JSONB, nullable=False),
        schema="settings",
    )
    # SECURITY DEFINER: the runtime role has no INSERT on settings_change, only this trigger (run as the owner) writes
    # it. The search_path is pinned so the function cannot be redirected to look-alike objects.
    op.execute(
        """
        CREATE FUNCTION settings.settings_audit() RETURNS trigger
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
    )
    op.execute("REVOKE ALL ON FUNCTION settings.settings_audit() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER schedule_audit AFTER INSERT OR UPDATE ON settings.schedule "
        "FOR EACH ROW EXECUTE FUNCTION settings.settings_audit()"
    )
    op.create_table(
        "conversation",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("target", sa.String(64)),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("partial", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("expires_at", _TZ, nullable=False),
        sa.CheckConstraint("id = 1", name="ck_conversation_single_row"),
        sa.CheckConstraint("kind IN ('snooze', 'reply', 'settings')", name="ck_conversation_kind"),
    )
    op.add_column("alert", sa.Column("release_at", _TZ))


def downgrade() -> None:
    """Remove all of it; ``alert.awaiting_input`` and the mail data stay untouched."""
    op.drop_column("alert", "release_at")
    op.drop_table("conversation")
    op.execute("DROP SCHEMA settings CASCADE")
