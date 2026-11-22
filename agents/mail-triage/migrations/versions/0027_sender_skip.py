"""The count of mails skipped for a listed sender that Gmail did not vouch for (INT-008, U-label-structure-36).

``categories.sender_skip`` is derived from ``filing`` (source ``sender_rule_not_applied``): the agent updates it in the
transaction that writes the filing, so the api can show a count per list entry without any right on the agent-owned
filing table. It holds the mailbox, the list entry (a value the user typed), the count and the last time; never a
sender address, a subject or a message id. The time is the database's.

``purge_expired()`` also removes the entries without a skip in the last 90 days. The downgrade takes both away again.
Rights are in ``app/db/grants.sql``; the definer's table rights are granted here too, as the purge may run before that
file does.

Revision ID: 0027
Revises: 0026
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_SCHEMA = "categories"
_PURGE = "categories.purge_expired()"
_PART = """    DELETE FROM categories.sender_skip WHERE last_skipped_at < pg_catalog.now() - interval '90 days';
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed || jsonb_build_object('sender_skip', n);
"""
_MARK = "    -- A rejection lives until the list changes again.\n"


def _replace_purge(sql: str) -> None:
    # Only the owner of a function may replace it: take it back for the statement, then hand it over again.
    op.execute(f"ALTER FUNCTION {_PURGE} OWNER TO current_user")
    op.execute(sql)
    op.execute(f"ALTER FUNCTION {_PURGE} OWNER TO categories_definer")


def _current_purge() -> str:
    """The definition in the database now, so this revision builds on whatever the chain made of it."""
    statement = sa.text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))")
    return str(op.get_bind().execute(statement, {"name": _PURGE}).scalar_one())


def upgrade() -> None:
    """Create the table and add its retention to the purge."""
    op.create_table(
        "sender_skip",
        sa.Column("mailbox_id", sa.String(64), sa.ForeignKey("categories.mailbox.id"), nullable=False),
        sa.Column("entry", sa.Text, nullable=False),
        sa.Column("skipped", sa.Integer, nullable=False, server_default="1"),
        sa.Column("last_skipped_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("mailbox_id", "entry", name="pk_sender_skip"),
        sa.CheckConstraint("skipped >= 1", name="ck_sender_skip_positive"),
        sa.CheckConstraint("char_length(entry) BETWEEN 1 AND 320", name="ck_sender_skip_entry_length"),
        schema=_SCHEMA,
    )
    op.create_index("ix_sender_skip_last_skipped_at", "sender_skip", ["last_skipped_at"], schema=_SCHEMA)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON categories.sender_skip TO categories_definer")
    body = _current_purge()
    if body.count(_MARK) != 1:
        raise RuntimeError("the purge function has changed shape")
    _replace_purge(body.replace(_MARK, _PART + _MARK, 1))


def downgrade() -> None:
    """Take the retention step and the table away."""
    body = _current_purge()
    if _PART not in body:
        raise RuntimeError("the purge function does not hold the part of revision 0027")
    _replace_purge(body.replace(_PART, "", 1))
    op.drop_index("ix_sender_skip_last_skipped_at", table_name="sender_skip", schema=_SCHEMA)
    op.drop_table("sender_skip", schema=_SCHEMA)
