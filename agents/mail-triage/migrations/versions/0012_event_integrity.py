"""Event integrity (INT-002, ADR-0025, ADR-0030, ADR-0033, ADR-0039; SEC2-02, SEC2-03, RT2-06, RT2-09).

Upgrade:
- ``settings.contract_version()`` returns 2: the api's readiness probe now answers 503 on a database that is still at
  0009 to 0011 (version 1), and an api of an older build answers 503 on this one. The api's
  ``EXPECTED_CONTRACT_VERSION`` is raised in the same change.
- ``web_auth.security_event`` gets ``CHECK (count >= 1)`` and a ``BEFORE UPDATE`` trigger that allows one change only:
  ``count`` rises by exactly one with every other column unchanged. A web role that is taken over can no longer lower
  or jump the count of the wrong-code alert; the owner is held to the same rule.
- the index ``(kind, at)`` serves the alert query of the agent.
The agent role's column-level ``SELECT (id, kind, at, count)`` is in ``app/db/grants.sql``.

Downgrade: trigger, function, check and index go; the function returns 1 again. Event data stays.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_CONTRACT = (
    "CREATE OR REPLACE FUNCTION settings.contract_version() RETURNS integer "
    "LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$ SELECT {version} $$"
)
_GUARD = """
CREATE FUNCTION web_auth.security_event_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NEW.count IS DISTINCT FROM OLD.count + 1
        OR (to_jsonb(NEW) - 'count') IS DISTINCT FROM (to_jsonb(OLD) - 'count') THEN
        RAISE EXCEPTION 'a security event may only have its count raised by one' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END
$$
"""
_TRIGGER = (
    "CREATE TRIGGER security_event_guard BEFORE UPDATE ON web_auth.security_event "
    "FOR EACH ROW EXECUTE FUNCTION web_auth.security_event_guard()"
)


def upgrade() -> None:
    """Raise the contract version, guard the count, add the check and the index."""
    op.execute(_CONTRACT.format(version=2))
    op.execute(_GUARD)
    op.execute("REVOKE ALL ON FUNCTION web_auth.security_event_guard() FROM PUBLIC")
    op.execute(_TRIGGER)
    op.create_check_constraint("ck_security_event_count", "security_event", "count >= 1", schema="web_auth")
    op.create_index("ix_security_event_kind_at", "security_event", ["kind", "at"], schema="web_auth")


def downgrade() -> None:
    """Remove the index, the check and the trigger; the contract version is 1 again."""
    op.drop_index("ix_security_event_kind_at", table_name="security_event", schema="web_auth")
    op.drop_constraint("ck_security_event_count", "security_event", schema="web_auth")
    op.execute("DROP TRIGGER security_event_guard ON web_auth.security_event")
    op.execute("DROP FUNCTION web_auth.security_event_guard()")
    op.execute(_CONTRACT.format(version=1))
