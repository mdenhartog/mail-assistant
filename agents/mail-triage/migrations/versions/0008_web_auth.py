"""Web sign-in and settings (INT-002, ADR-0033, ADR-0036): the ``web_auth`` schema, the web line of the guard.

Upgrade:
- schema ``web_auth`` with ``login_request`` (e-mailed code, kept dead for an hour so the hourly cap can be counted),
  ``session``, ``security_event`` (a CHECK-constrained kind, no free text) and the single-row ``web_lock``;
- the guard of 0006 gains the web line: the login role ``web_settings_runtime`` writes as channel ``web``, its
  ``updated_by`` must match ``^web:[0-9a-f]{32}$``, and the version still rises by exactly one;
- ``poll_state.web_notice_version`` (the cursor of announced web changes) and ``web_notice_token`` (the own Undo token
  record of a web notice);
- ``settings.contract_version()``, which the api's readiness probe checks instead of the Alembic head.
Every new function is revoked from PUBLIC and pins its search_path. Grants are in ``app/db/grants.sql`` (U-07).

Downgrade: all of it goes; the guard returns to its 0006 form. Settings data stays.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)
_KINDS = (
    "code_refused",
    "code_request_refused",
    "mail_failed",
    "session_start",
    "session_end",
    "csrf_refused",
    "rate_limited",
    "lock_refused",
)

_GUARD_TEMPLATE = """
CREATE OR REPLACE FUNCTION settings.schedule_guard() RETURNS trigger
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
{web_line}    END;
    IF channel IS NOT NULL AND NEW.updated_via IS DISTINCT FROM channel THEN
        RAISE EXCEPTION 'this database role may only write as %', channel USING ERRCODE = '42501';
    END IF;
{actor_check}    NEW.updated_at := now();
    RETURN NEW;
END
$$
"""

_GUARD_0008 = _GUARD_TEMPLATE.format(
    web_line="        WHEN 'web_settings_runtime' THEN 'web'\n",
    actor_check=(
        "    IF channel = 'web' AND NEW.updated_by !~ '^web:[0-9a-f]{32}$' THEN\n"
        "        RAISE EXCEPTION 'the web actor must be web:<32 hex>' USING ERRCODE = '42501';\n"
        "    END IF;\n"
    ),
)
_GUARD_0006 = _GUARD_TEMPLATE.format(web_line="", actor_check="")

_CONTRACT_VERSION = """
CREATE FUNCTION settings.contract_version() RETURNS integer
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$ SELECT 1 $$
"""


def upgrade() -> None:
    """Create the web tables, the cursor, the notice token record, the contract version and the web guard line."""
    op.execute("CREATE SCHEMA web_auth")
    op.create_table(
        "login_request",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("username_key", sa.CHAR(64), nullable=False),
        sa.Column("code_hash", sa.CHAR(64), nullable=False),
        sa.Column("expires_at", _TZ, nullable=False),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("created_at", _TZ, nullable=False),
        sa.Column("sent_at", _TZ),
        sa.Column("dead_at", _TZ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_login_request_attempts"),
        schema="web_auth",
    )
    op.create_table(
        "session",
        sa.Column("id_hash", sa.CHAR(64), primary_key=True),
        sa.Column("username_hash", sa.CHAR(64), nullable=False),
        sa.Column("last_seen_at", _TZ, nullable=False),
        sa.Column("absolute_expires_at", _TZ, nullable=False),
        schema="web_auth",
    )
    op.create_table(
        "security_event",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("username_hash", sa.CHAR(64)),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("client_key", sa.String(64), nullable=False),
        sa.Column("window", sa.BigInteger, nullable=False),
        sa.CheckConstraint("kind IN (" + ", ".join(f"'{k}'" for k in _KINDS) + ")", name="ck_security_event_kind"),
        sa.CheckConstraint("result IN ('ok', 'refused', 'failed')", name="ck_security_event_result"),
        sa.UniqueConstraint("kind", "client_key", "window", name="uq_security_event_kind_client_window"),
        schema="web_auth",
    )
    op.create_table(
        "web_lock",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("locked_at", _TZ, nullable=False),
        sa.CheckConstraint("id = 1", name="ck_web_lock_single_row"),
        schema="web_auth",
    )
    op.add_column("poll_state", sa.Column("web_notice_version", sa.Integer))
    op.create_table(
        "web_notice_token",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("before", postgresql.JSONB, nullable=False),
        sa.Column("created_at", _TZ, nullable=False),
        sa.Column("expires_at", _TZ, nullable=False),
    )
    op.execute(_CONTRACT_VERSION)
    op.execute("REVOKE ALL ON FUNCTION settings.contract_version() FROM PUBLIC")
    op.execute(_GUARD_0008)
    op.execute("REVOKE ALL ON FUNCTION settings.schedule_guard() FROM PUBLIC")


def downgrade() -> None:
    """Remove everything this revision added; the guard is the one of 0006 again."""
    op.execute(_GUARD_0006)
    op.execute("REVOKE ALL ON FUNCTION settings.schedule_guard() FROM PUBLIC")
    op.execute("DROP FUNCTION settings.contract_version()")
    op.drop_table("web_notice_token")
    op.drop_column("poll_state", "web_notice_version")
    op.execute("DROP SCHEMA web_auth CASCADE")
