"""Mail categories, list half (INT-004, ADR-0042, ADR-0043, ADR-0047): the schema ``categories``.

Upgrade: schema ``categories`` with ``mailbox`` (the id only), ``category_identity``, ``list_version``, ``category``,
``list_audit``, ``category_count``, ``gmail_label``, ``category_label``, ``filing``, ``list_cursor``, ``rejection``,
``telegram_action`` and ``apply_config``. Every table has ``mailbox_id`` first in its primary key. The plan, decision
and approval tables come with the R2 revision. Rights are in ``app/db/grants.sql``; nothing is granted here.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_SCHEMA = "categories"
_TZ = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def _mailbox() -> sa.Column[str]:
    """The mailbox id of ADR-0043: first column of every key."""
    return sa.Column("mailbox_id", sa.String(64), sa.ForeignKey("categories.mailbox.id"), nullable=False)


def _create_list_tables() -> None:
    op.create_table("mailbox", sa.Column("id", sa.String(64), primary_key=True), schema=_SCHEMA)
    op.create_table(
        "category_identity",
        _mailbox(),
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("created_at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "id", name="pk_category_identity"),
        schema=_SCHEMA,
    )
    op.create_table(
        "list_version",
        _mailbox(),
        sa.Column("version", sa.Integer, nullable=False),
        # created_at, created_via and created_by are derived by a trigger, never supplied by the writer (ADR-0030).
        sa.Column("created_at", _TZ, nullable=False, server_default=_NOW),
        sa.Column("created_via", sa.String(16), nullable=False),
        sa.Column("created_by", sa.CHAR(64), nullable=False),
        sa.PrimaryKeyConstraint("mailbox_id", "version", name="pk_list_version"),
        sa.CheckConstraint("version >= 1", name="ck_list_version_positive"),
        sa.CheckConstraint("created_via IN ('telegram', 'web', 'operator')", name="ck_list_version_via"),
        schema=_SCHEMA,
    )
    op.create_table(
        "category",
        sa.Column("mailbox_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.PrimaryKeyConstraint("mailbox_id", "version", "id", name="pk_category"),
        sa.ForeignKeyConstraint(
            ["mailbox_id", "version"],
            ["categories.list_version.mailbox_id", "categories.list_version.version"],
            name="fk_category_list_version",
        ),
        sa.ForeignKeyConstraint(
            ["mailbox_id", "id"],
            ["categories.category_identity.mailbox_id", "categories.category_identity.id"],
            name="fk_category_identity",
        ),
        sa.UniqueConstraint("mailbox_id", "version", "position", name="uq_category_position"),
        sa.UniqueConstraint("mailbox_id", "version", "name", name="uq_category_name"),
        # Backstops of category-policy (NAME_MAX, DESCRIPTION_MAX, MAX_CATEGORIES); the policy package is the rule.
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="ck_category_name_length"),
        sa.CheckConstraint("char_length(description) <= 500", name="ck_category_description_length"),
        sa.CheckConstraint("position BETWEEN 0 AND 49", name="ck_category_position"),
        schema=_SCHEMA,
    )
    op.create_table(
        "list_audit",
        _mailbox(),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("old_list", postgresql.JSONB, nullable=False),
        sa.Column("new_list", postgresql.JSONB, nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("actor_digest", sa.CHAR(64), nullable=False),
        sa.Column("at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "version", name="pk_list_audit"),
        schema=_SCHEMA,
    )


def _create_derived_tables() -> None:
    op.create_table(
        "category_count",
        _mailbox(),
        # The nil UUID stands for the built-in "Other"; no foreign key, the counts are replaced each cycle.
        sa.Column("category_id", sa.Uuid, nullable=False),
        sa.Column("mail_count", sa.Integer, nullable=False),
        sa.Column("counted_at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "category_id", name="pk_category_count"),
        sa.CheckConstraint("mail_count >= 0", name="ck_category_count_positive"),
        schema=_SCHEMA,
    )
    op.create_table(
        "gmail_label",
        _mailbox(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("seen_at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "name", name="pk_gmail_label"),
        schema=_SCHEMA,
    )
    op.create_table(
        "category_label",
        sa.Column("mailbox_id", sa.String(64), nullable=False),
        sa.Column("category_id", sa.Uuid, nullable=False),
        sa.Column("label_id", sa.String(64), nullable=False),
        sa.Column("label_name", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("mailbox_id", "category_id", name="pk_category_label"),
        sa.ForeignKeyConstraint(
            ["mailbox_id", "category_id"],
            ["categories.category_identity.mailbox_id", "categories.category_identity.id"],
            name="fk_category_label_identity",
        ),
        sa.UniqueConstraint("mailbox_id", "label_id", name="uq_category_label_label"),
        schema=_SCHEMA,
    )


def _create_agent_tables() -> None:
    op.create_table(
        "filing",
        _mailbox(),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("list_version", sa.Integer, nullable=False),
        # No sender and no subject (AC-22). The nil UUID stands for "Other". No foreign keys: the retention of a
        # filing (1 year after it) is independent of the one of a list version.
        sa.Column("category_id", sa.Uuid, nullable=False),
        sa.Column("filed_at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "message_id", "list_version", name="pk_filing"),
        schema=_SCHEMA,
    )
    op.create_index("ix_filing_filed_at", "filing", ["mailbox_id", "filed_at"], schema=_SCHEMA)
    op.create_table(
        "list_cursor",
        _mailbox(),
        sa.Column("last_version", sa.Integer, nullable=False),
        sa.Column("advanced_at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", name="pk_list_cursor"),
        sa.CheckConstraint("last_version >= 0", name="ck_list_cursor_positive"),
        schema=_SCHEMA,
    )
    op.create_table(
        "rejection",
        _mailbox(),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("list_version", sa.Integer, nullable=False),
        sa.Column("rejected_at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "message_id", name="pk_rejection"),
        schema=_SCHEMA,
    )
    op.create_table(
        "telegram_action",
        _mailbox(),
        sa.Column("nonce_hash", sa.CHAR(64), nullable=False),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("created_at", _TZ, nullable=False, server_default=_NOW),
        sa.Column("expires_at", _TZ, nullable=False),
        sa.Column("used_at", _TZ),
        sa.PrimaryKeyConstraint("mailbox_id", "nonce_hash", name="pk_telegram_action"),
        sa.CheckConstraint("kind IN ('undo', 'cancel', 'move_back', 'lock')", name="ck_telegram_action_kind"),
        schema=_SCHEMA,
    )
    op.create_index("ix_telegram_action_expires_at", "telegram_action", ["mailbox_id", "expires_at"], schema=_SCHEMA)
    op.create_table(
        "apply_config",
        _mailbox(),
        sa.Column("threshold", sa.Integer, nullable=False),
        sa.Column("delay_minutes", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("mailbox_id", name="pk_apply_config"),
        sa.CheckConstraint("threshold >= 1", name="ck_apply_config_threshold"),
        sa.CheckConstraint("delay_minutes >= 0", name="ck_apply_config_delay"),
        schema=_SCHEMA,
    )


# Refusals use 42501 (insufficient_privilege), like the settings guard of 0006: the write is not allowed.
# The channel follows the database login, never the writer's claim (ADR-0030): one line per login role that may write.
# The actor digest is derived from the same login; neither is a column the writer may name.
_DERIVE = """
CREATE FUNCTION categories.list_version_derive() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    NEW.created_at := now();
    NEW.created_via := CASE session_user
        WHEN 'mail_triage_runtime' THEN 'telegram'
        WHEN 'web_settings_runtime' THEN 'web'
        ELSE 'operator'
    END;
    NEW.created_by := encode(sha256(convert_to(session_user::text, 'UTF8')), 'hex');
    RETURN NEW;
END
$$
"""

# A new version must be the mailbox's latest and exactly one above the one before it (no gap, no second writer slipping
# a number in). Deferred, so it judges the transaction as a whole.
_VERSION_CHECK = """
CREATE FUNCTION categories.list_version_check() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NEW.version - 1 IS DISTINCT FROM coalesce(
            (SELECT max(v.version) FROM categories.list_version v
              WHERE v.mailbox_id = NEW.mailbox_id AND v.version < NEW.version), 0)
        OR EXISTS (SELECT 1 FROM categories.list_version v
                    WHERE v.mailbox_id = NEW.mailbox_id AND v.version > NEW.version) THEN
        RAISE EXCEPTION 'a list version must follow the latest one by exactly one' USING ERRCODE = '42501';
    END IF;
    RETURN NULL;
END
$$
"""

# Category rows exist only for a version created in this very transaction (xmin is the writing transaction's id and
# cannot be set by a writer). Deferred, so the version row may be inserted first.
_CATEGORY_CHECK = """
CREATE FUNCTION categories.category_check() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM categories.list_version v
                    WHERE v.mailbox_id = NEW.mailbox_id AND v.version = NEW.version
                      AND v.xmin = pg_current_xact_id()::xid) THEN
        RAISE EXCEPTION 'categories may only be added to a list version created in the same transaction'
            USING ERRCODE = '42501';
    END IF;
    RETURN NULL;
END
$$
"""

_LIST_JSON = """
CREATE FUNCTION categories.list_json(mailbox text, wanted integer) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT coalesce(
        jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name, 'description', c.description, 'position', c.position)
                  ORDER BY c.position),
        '[]'::jsonb)
    FROM categories.category c WHERE c.mailbox_id = mailbox AND c.version = wanted
$$
"""

# SECURITY DEFINER: neither runtime role has INSERT on list_audit, only this trigger (run as the owner) writes it. It is
# deferred so every category row of the version is there; channel and actor come from the version row the database
# derived. One version, one audit record.
_AUDIT = """
CREATE FUNCTION categories.list_audit_write() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    INSERT INTO categories.list_audit (mailbox_id, version, old_list, new_list, channel, actor_digest, at)
    VALUES (
        NEW.mailbox_id, NEW.version,
        categories.list_json(NEW.mailbox_id, coalesce(
            (SELECT max(v.version) FROM categories.list_version v
              WHERE v.mailbox_id = NEW.mailbox_id AND v.version < NEW.version), 0)),
        categories.list_json(NEW.mailbox_id, NEW.version),
        NEW.created_via, NEW.created_by, now()
    );
    RETURN NULL;
END
$$
"""

# The retention purge (ADR-0047): the owner's, no parameters, the database clock only. Whatever a caller sets in its
# session (time zone, search path, a look-alike now()), the pinned path and the pg_catalog clock decide.
_PURGE = """
CREATE FUNCTION categories.purge_expired() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    removed jsonb := '{}'::jsonb;
    n bigint;
    m bigint;
BEGIN
    DELETE FROM categories.list_audit WHERE at < pg_catalog.now() - interval '1 year';
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed || jsonb_build_object('list_audit', n);
    DELETE FROM categories.filing WHERE filed_at < pg_catalog.now() - interval '1 year';
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed || jsonb_build_object('filing', n);
    DELETE FROM categories.telegram_action WHERE expires_at < pg_catalog.now() - interval '7 days';
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed || jsonb_build_object('telegram_action', n);
    -- A rejection lives until the list changes again.
    DELETE FROM categories.rejection r
     WHERE r.list_version < (SELECT max(v.version) FROM categories.list_version v WHERE v.mailbox_id = r.mailbox_id);
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed || jsonb_build_object('rejection', n);
    -- A version goes one year after its successor was created; the latest version never goes.
    -- Versions are consecutive (the deferred check), so the successor of version v is v + 1.
    WITH expired AS (
        SELECT v.mailbox_id, v.version FROM categories.list_version v
         WHERE EXISTS (SELECT 1 FROM categories.list_version nxt
                        WHERE nxt.mailbox_id = v.mailbox_id AND nxt.version = v.version + 1
                          AND nxt.created_at < pg_catalog.now() - interval '1 year')
    ), gone_category AS (
        DELETE FROM categories.category c USING expired e
         WHERE c.mailbox_id = e.mailbox_id AND c.version = e.version RETURNING 1
    ), gone_version AS (
        DELETE FROM categories.list_version v USING expired e
         WHERE v.mailbox_id = e.mailbox_id AND v.version = e.version RETURNING 1
    )
    SELECT (SELECT count(*) FROM gone_category), (SELECT count(*) FROM gone_version) INTO n, m;
    RETURN removed || jsonb_build_object('category', n, 'list_version', m);
END
$$
"""

_TRIGGERS = (
    "CREATE TRIGGER list_version_derive BEFORE INSERT ON categories.list_version "
    "FOR EACH ROW EXECUTE FUNCTION categories.list_version_derive()",
    "CREATE CONSTRAINT TRIGGER list_version_check AFTER INSERT ON categories.list_version "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION categories.list_version_check()",
    "CREATE CONSTRAINT TRIGGER list_version_audit AFTER INSERT ON categories.list_version "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION categories.list_audit_write()",
    "CREATE CONSTRAINT TRIGGER category_check AFTER INSERT ON categories.category "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION categories.category_check()",
)
_FUNCTIONS = (
    "categories.list_version_derive()",
    "categories.list_version_check()",
    "categories.category_check()",
    "categories.list_json(text, integer)",
    "categories.list_audit_write()",
    "categories.purge_expired()",
)


def upgrade() -> None:
    """Create the schema, the list-half tables, the triggers and the owner's functions."""
    op.execute(f"CREATE SCHEMA {_SCHEMA}")
    _create_list_tables()
    _create_derived_tables()
    _create_agent_tables()
    for statement in (_DERIVE, _VERSION_CHECK, _CATEGORY_CHECK, _LIST_JSON, _AUDIT, _PURGE, *_TRIGGERS):
        op.execute(statement)
    for function in _FUNCTIONS:  # grants.sql gives EXECUTE to the one role that needs each; nothing is public
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
    # The api's readiness probe tests "contract version at least X", so a later revision does not break an older api.
    op.execute(
        "CREATE FUNCTION categories.contract_version() RETURNS integer "
        "LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$ SELECT 1 $$"
    )
    op.execute("REVOKE ALL ON FUNCTION categories.contract_version() FROM PUBLIC")


def downgrade() -> None:
    """Remove the whole schema, its tables and functions; no other schema is touched."""
    op.execute(f"DROP SCHEMA {_SCHEMA} CASCADE")
