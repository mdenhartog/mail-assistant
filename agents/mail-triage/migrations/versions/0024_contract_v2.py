"""The category contract v2, additive half (INT-008, U-label-structure-05, ADR-0025, ADR-0053, ADR-0058, ADR-0059).

Upgrade, every step with defaults so the running agent keeps working on the old columns:

- ``category.kind`` (``topic`` or ``extra``, default ``topic``) and ``category.notify`` (default false): every existing
  category becomes a topic without a tick.
- ``category_sender`` and ``list_settings``: insert-only, per list version, with the same deferred version trigger and
  the same ``(mailbox_id, version)`` rules as ``category``. ``list_settings`` gets one row per existing version, with
  the archive label the migrate job read from its environment (default ``Assistant/Archive``). No list version and no
  audit record is inserted.
- ``upload_preview``: the preview of a YAML upload, written and consumed by the api.
- ``filing``: ``topic_id`` (filled from ``category_id`` and kept in step with it by a bridge trigger until the unit
  that switches the code drops ``category_id``), ``extra_id``, ``source`` (default ``model``) and ``source_ref``.
- ``purge_expired()`` also removes expired previews, and the senders and settings of a version it removes.

An alert is written once per mail: ``alert.mail_item_id`` has been unique since revision 0001, so no key is added.

The downgrade removes only what this revision added. Rights are in ``app/db/grants.sql``; nothing is granted here.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

_SCHEMA = "categories"
_TZ = sa.DateTime(timezone=True)
_NOW = sa.text("now()")
_DEFAULT_ARCHIVE_LABEL = "Assistant/Archive"
_PURGE = "categories.purge_expired()"

# The deferred check of revision 0014 reads only NEW.mailbox_id and NEW.version, so the senders and the settings of a
# version use the very same function: rows exist only for a version created in the same transaction.
_VERSION_TRIGGER = (
    "CREATE CONSTRAINT TRIGGER {table}_check AFTER INSERT ON categories.{table} "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION categories.category_check()"
)

# During the expand phase the code still writes ``category_id`` only; the topic follows it.
_BRIDGE_FUNCTION = """
CREATE FUNCTION categories.filing_topic_bridge() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    NEW.topic_id := coalesce(NEW.topic_id, NEW.category_id);
    RETURN NEW;
END
$$
"""
_BRIDGE_TRIGGER = (
    "CREATE TRIGGER filing_topic_bridge BEFORE INSERT ON categories.filing "
    "FOR EACH ROW EXECUTE FUNCTION categories.filing_topic_bridge()"
)

# An expired preview goes one hour after it expired (design: purged after 1 hour).
_PREVIEW_PART = """    DELETE FROM categories.upload_preview WHERE expires_at < pg_catalog.now() - interval '1 hour';
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed || jsonb_build_object('upload_preview', n);
"""
_PREVIEW_MARK = "    -- A rejection lives until the list changes again.\n"
# The senders and the settings of an expired version go in the same statement as its categories and the version.
_VERSION_PART = """    ), gone_sender AS (
        DELETE FROM categories.category_sender s USING expired e
         WHERE s.mailbox_id = e.mailbox_id AND s.version = e.version RETURNING 1
    ), gone_settings AS (
        DELETE FROM categories.list_settings l USING expired e
         WHERE l.mailbox_id = e.mailbox_id AND l.version = e.version RETURNING 1
"""
_VERSION_MARK = "    ), gone_category AS (\n"


def _archive_label() -> str:
    """The label the migrate job read from its environment; the default when the job did not pass one."""
    config = op.get_context().config
    value = config.attributes.get("archive_label") if config is not None else None
    return str(value) if value else _DEFAULT_ARCHIVE_LABEL


def _replace_purge(sql: str) -> None:
    # Only the owner of a function may replace it: take it back for the statement, then hand it over again.
    op.execute(f"ALTER FUNCTION {_PURGE} OWNER TO current_user")
    op.execute(sql)
    op.execute(f"ALTER FUNCTION {_PURGE} OWNER TO categories_definer")


def _current_purge() -> str:
    """The definition in the database now, so this revision builds on whatever the chain made of it."""
    statement = sa.text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))")
    definition = op.get_bind().execute(statement, {"name": _PURGE}).scalar_one()
    return str(definition)


def _patched_purge(body: str) -> str:
    for mark in (_PREVIEW_MARK, _VERSION_MARK):
        if body.count(mark) != 1:
            raise RuntimeError("the purge function has changed shape")
    return body.replace(_PREVIEW_MARK, _PREVIEW_PART + _PREVIEW_MARK, 1).replace(
        _VERSION_MARK, _VERSION_PART + _VERSION_MARK, 1
    )


def _original_purge(body: str) -> str:
    if _PREVIEW_PART not in body or _VERSION_PART not in body:
        raise RuntimeError("the purge function does not hold the parts of revision 0024")
    return body.replace(_PREVIEW_PART, "", 1).replace(_VERSION_PART, "", 1)


def _mailbox() -> sa.Column[str]:
    return sa.Column("mailbox_id", sa.String(64), sa.ForeignKey("categories.mailbox.id"), nullable=False)


def _alter_category() -> None:
    op.add_column("category", sa.Column("kind", sa.String(8), nullable=False, server_default="topic"), schema=_SCHEMA)
    op.add_column(
        "category", sa.Column("notify", sa.Boolean, nullable=False, server_default=sa.false()), schema=_SCHEMA
    )
    op.create_check_constraint("ck_category_kind", "category", "kind IN ('topic', 'extra')", schema=_SCHEMA)


def _create_list_settings() -> None:
    op.create_table(
        "list_settings",
        sa.Column("mailbox_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("general_instructions", sa.Text, nullable=False, server_default=""),
        sa.Column("archive_label", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("mailbox_id", "version", name="pk_list_settings"),
        sa.ForeignKeyConstraint(
            ["mailbox_id", "version"],
            ["categories.list_version.mailbox_id", "categories.list_version.version"],
            name="fk_list_settings_list_version",
        ),
        sa.CheckConstraint("char_length(general_instructions) <= 4000", name="ck_list_settings_instructions"),
        sa.CheckConstraint("char_length(archive_label) BETWEEN 1 AND 225", name="ck_list_settings_archive_label"),
        schema=_SCHEMA,
    )
    # The existing versions get their row before the trigger exists: the trigger accepts only a version of its own
    # transaction. Not a list version and not an audit record: the settings of a version are part of it.
    op.get_bind().execute(
        sa.text(
            "INSERT INTO categories.list_settings (mailbox_id, version, archive_label) "
            "SELECT mailbox_id, version, :label FROM categories.list_version"
        ),
        {"label": _archive_label()},
    )
    op.execute(_VERSION_TRIGGER.format(table="list_settings"))


def _create_category_sender() -> None:
    op.create_table(
        "category_sender",
        sa.Column("mailbox_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("category_id", sa.Uuid, nullable=False),
        sa.Column("entry", sa.Text, nullable=False),
        sa.Column("is_domain", sa.Boolean, nullable=False),
        sa.Column("subdomains", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("mailbox_id", "version", "category_id", "entry", name="pk_category_sender"),
        sa.ForeignKeyConstraint(
            ["mailbox_id", "version", "category_id"],
            ["categories.category.mailbox_id", "categories.category.version", "categories.category.id"],
            name="fk_category_sender_category",
        ),
        # Backstops; category-policy is the rule (a domain is at most 253 characters, an address at most 254).
        sa.CheckConstraint("char_length(entry) BETWEEN 1 AND 320", name="ck_category_sender_entry_length"),
        sa.CheckConstraint("is_domain OR NOT subdomains", name="ck_category_sender_subdomains"),
        schema=_SCHEMA,
    )
    op.execute(_VERSION_TRIGGER.format(table="category_sender"))


def _create_upload_preview() -> None:
    op.create_table(
        "upload_preview",
        _mailbox(),
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("session_digest", sa.CHAR(64), nullable=False),
        sa.Column("file_hash", sa.CHAR(64), nullable=False),
        sa.Column("base_version", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", _TZ, nullable=False, server_default=_NOW),
        sa.Column("expires_at", _TZ, nullable=False),
        sa.Column("used_at", _TZ),
        sa.PrimaryKeyConstraint("mailbox_id", "id", name="pk_upload_preview"),
        sa.CheckConstraint("base_version >= 0", name="ck_upload_preview_base_version"),
        schema=_SCHEMA,
    )
    op.create_index("ix_upload_preview_expires_at", "upload_preview", ["expires_at"], schema=_SCHEMA)


def _alter_filing() -> None:
    op.add_column("filing", sa.Column("topic_id", sa.Uuid), schema=_SCHEMA)
    op.execute("UPDATE categories.filing SET topic_id = category_id")
    op.alter_column("filing", "topic_id", nullable=False, schema=_SCHEMA)
    op.add_column("filing", sa.Column("extra_id", sa.Uuid), schema=_SCHEMA)
    op.add_column("filing", sa.Column("source", sa.String(24), nullable=False, server_default="model"), schema=_SCHEMA)
    op.add_column("filing", sa.Column("source_ref", sa.Text), schema=_SCHEMA)
    op.create_check_constraint(
        "ck_filing_source", "filing", "source IN ('model', 'sender_rule', 'sender_rule_not_applied')", schema=_SCHEMA
    )
    op.create_check_constraint(
        "ck_filing_source_ref_length", "filing", "char_length(source_ref) <= 320", schema=_SCHEMA
    )
    op.execute(_BRIDGE_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION categories.filing_topic_bridge() FROM PUBLIC")
    op.execute(_BRIDGE_TRIGGER)


def upgrade() -> None:
    """Add the v2 columns and tables with defaults; nothing the running agent reads is dropped or renamed."""
    _alter_category()
    _create_list_settings()
    _create_category_sender()
    _create_upload_preview()
    _alter_filing()
    # The definer's table rights are kept current by grants.sql; the purge below may run before that file does.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON categories.category_sender, categories.list_settings, "
        "categories.upload_preview TO categories_definer"
    )
    _replace_purge(_patched_purge(_current_purge()))


def downgrade() -> None:
    """Remove what upgrade made; ``category_id`` was never touched, so the old shape is back."""
    _replace_purge(_original_purge(_current_purge()))
    op.execute("DROP TRIGGER filing_topic_bridge ON categories.filing")
    op.execute("DROP FUNCTION categories.filing_topic_bridge()")
    op.drop_constraint("ck_filing_source_ref_length", "filing", schema=_SCHEMA, type_="check")
    op.drop_constraint("ck_filing_source", "filing", schema=_SCHEMA, type_="check")
    for column in ("source_ref", "source", "extra_id", "topic_id"):
        op.drop_column("filing", column, schema=_SCHEMA)
    op.drop_table("upload_preview", schema=_SCHEMA)
    op.drop_table("category_sender", schema=_SCHEMA)
    op.drop_table("list_settings", schema=_SCHEMA)
    op.drop_constraint("ck_category_kind", "category", schema=_SCHEMA, type_="check")
    op.drop_column("category", "notify", schema=_SCHEMA)
    op.drop_column("category", "kind", schema=_SCHEMA)
