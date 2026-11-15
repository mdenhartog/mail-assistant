"""Mail categories, list half (INT-004, ADR-0042, ADR-0043, ADR-0047): the schema ``categories``.

Upgrade: schema ``categories`` with ``mailbox`` (the id only), ``category_identity``, ``list_version``, ``category``,
``list_audit``, ``category_count``, ``gmail_label``, ``category_label``, ``filing``, ``list_cursor``, ``rejection``,
``telegram_action`` and ``apply_config``. Every table has ``mailbox_id`` first in its primary key. The plan, decision and
approval tables come with the R2 revision. Rights are in ``app/db/grants.sql``; nothing is granted here.

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


def upgrade() -> None:
    """Create the schema and the list-half tables."""
    op.execute(f"CREATE SCHEMA {_SCHEMA}")
    _create_list_tables()
    _create_derived_tables()
    _create_agent_tables()
    # The api's readiness probe tests "contract version at least X", so a later revision does not break an older api.
    op.execute(
        "CREATE FUNCTION categories.contract_version() RETURNS integer "
        "LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$ SELECT 1 $$"
    )
    op.execute("REVOKE ALL ON FUNCTION categories.contract_version() FROM PUBLIC")


def downgrade() -> None:
    """Remove the whole schema, its tables and functions; no other schema is touched."""
    op.execute(f"DROP SCHEMA {_SCHEMA} CASCADE")
