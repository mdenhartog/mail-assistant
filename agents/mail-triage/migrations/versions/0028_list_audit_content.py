"""The list audit records what a list holds besides names (INT-008, U-label-structure-14, ADR-0043, ADR-0053).

``categories.list_json`` also gives each category's ``kind``, ``notify`` and its senders (ordered by entry, so one list
always reads the same), and a new pair of columns on ``list_audit``, ``old_instructions`` and ``new_instructions``,
holds the general instructions of the two lists. A change of a tick, a sender or the instructions alone now leaves a
trace. The ``id``, ``name``, ``description`` and ``position`` keys stay as they were, so the Telegram change notice and
the api read the audit as before. The audit holds the confirmed list itself by design (ADR-0043), never mail text.

``list_audit_write`` is replaced to fill the two columns; both functions keep their owner and their rights
(``CREATE OR REPLACE``). The downgrade puts the functions of revision 0014 back and drops the columns.

Revision ID: 0028
Revises: 0027
"""
# ruff: noqa: S608  # fixed DDL text, never built from input

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_LIST_JSON_HEAD = "CREATE OR REPLACE FUNCTION categories.list_json(mailbox text, wanted integer) RETURNS jsonb"

_NEW_LIST_JSON = (
    _LIST_JSON_HEAD
    + """
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT coalesce(
        jsonb_agg(jsonb_build_object(
            'id', c.id, 'name', c.name, 'description', c.description, 'position', c.position,
            'kind', c.kind, 'notify', c.notify,
            'senders', coalesce((
                SELECT jsonb_agg(jsonb_build_object('entry', s.entry, 'is_domain', s.is_domain,
                                                    'subdomains', s.subdomains) ORDER BY s.entry)
                  FROM categories.category_sender s
                 WHERE s.mailbox_id = c.mailbox_id AND s.version = c.version AND s.category_id = c.id),
                '[]'::jsonb)
        ) ORDER BY c.position),
        '[]'::jsonb)
    FROM categories.category c WHERE c.mailbox_id = mailbox AND c.version = wanted
$$
"""
)

_OLD_LIST_JSON = (
    _LIST_JSON_HEAD
    + """
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT coalesce(
        jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name, 'description', c.description, 'position', c.position)
                  ORDER BY c.position),
        '[]'::jsonb)
    FROM categories.category c WHERE c.mailbox_id = mailbox AND c.version = wanted
$$
"""
)

_AUDIT_HEAD = "CREATE OR REPLACE FUNCTION categories.list_audit_write() RETURNS trigger"

_NEW_AUDIT = (
    _AUDIT_HEAD
    + """
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    previous integer := coalesce(
        (SELECT max(v.version) FROM categories.list_version v
          WHERE v.mailbox_id = NEW.mailbox_id AND v.version < NEW.version), 0);
BEGIN
    INSERT INTO categories.list_audit (
        mailbox_id, version, old_list, new_list, old_instructions, new_instructions, channel, actor_digest, at)
    VALUES (
        NEW.mailbox_id, NEW.version,
        categories.list_json(NEW.mailbox_id, previous),
        categories.list_json(NEW.mailbox_id, NEW.version),
        coalesce((SELECT s.general_instructions FROM categories.list_settings s
                   WHERE s.mailbox_id = NEW.mailbox_id AND s.version = previous), ''),
        coalesce((SELECT s.general_instructions FROM categories.list_settings s
                   WHERE s.mailbox_id = NEW.mailbox_id AND s.version = NEW.version), ''),
        NEW.created_via, NEW.created_by, now()
    );
    RETURN NULL;
END
$$
"""
)

_OLD_AUDIT = (
    _AUDIT_HEAD
    + """
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
)


def upgrade() -> None:
    """Add the instruction columns (old rows read as empty), then the richer functions."""
    for column in ("old_instructions", "new_instructions"):
        op.add_column("list_audit", sa.Column(column, sa.Text, nullable=False, server_default=""), schema="categories")
    op.execute(_NEW_LIST_JSON)
    op.execute(_NEW_AUDIT)


def downgrade() -> None:
    """Restore the functions of revision 0014, then drop the columns."""
    op.execute(_OLD_AUDIT)
    op.execute(_OLD_LIST_JSON)
    for column in ("new_instructions", "old_instructions"):
        op.drop_column("list_audit", column, schema="categories")
