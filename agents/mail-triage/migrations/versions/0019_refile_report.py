"""The table of the daily re-file report (INT-004, U-mail-categories-25, AC-46, ADR-0043, ADR-0047).

- ``categories.refile_report``: one row per daily run with counts only (AC-30: no sender, subject or message id).
  ``mailbox_id`` is first in the key and the index (ADR-0043). The time is the database's.
- ``categories.record_refile_report`` (SECURITY DEFINER, owned by the non-login ``categories_definer``): the agent role
  has no right on the table at all; it can only append a row through this function.
- ``purge_expired()`` also deletes report rows older than one year, like the other audit tables (ADR-0047).

Rights are in ``app/db/grants.sql``; nothing is granted here.

Revision ID: 0019
Revises: 0018
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_SCHEMA = "categories"
_TZ = sa.DateTime(timezone=True)
_FUNCTION = "categories.record_refile_report(text, integer, integer, integer, integer, integer)"
_PURGE = "categories.purge_expired()"

_RECORD = """
CREATE FUNCTION categories.record_refile_report(
    p_mailbox text, p_filed integer, p_checked integer, p_refiled integer, p_in_other integer, p_gone integer
) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    INSERT INTO categories.refile_report (mailbox_id, filed, checked, refiled, in_other, gone)
    VALUES (p_mailbox, p_filed, p_checked, p_refiled, p_in_other, p_gone)
$$
"""

_PURGE_PART = """    DELETE FROM categories.refile_report WHERE at < pg_catalog.now() - interval '1 year';
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed || jsonb_build_object('refile_report', n);
"""
_MARK = "    -- A rejection lives until the list changes again.\n"


def _purge_before() -> str:
    """The purge of revision 0015 (which holds the one of 0014), read from that revision: one copy of the text."""
    path = Path(__file__).with_name("0015_categories_plan.py")
    spec = importlib.util.spec_from_file_location("categories_0015", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("revision 0015 cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module._purge_with_plan_half())


def _purge_with_report() -> str:
    body = _purge_before()
    if _MARK not in body:
        raise RuntimeError("the purge of revision 0015 has changed shape")
    return body.replace(_MARK, _PURGE_PART + _MARK, 1)


def _replace_purge(sql: str) -> None:
    # Only the owner of a function may replace it: take it back for the statement, then hand it over again.
    op.execute(f"ALTER FUNCTION {_PURGE} OWNER TO current_user")
    op.execute(sql)
    op.execute(f"ALTER FUNCTION {_PURGE} OWNER TO categories_definer")


def upgrade() -> None:
    """Create the table, the function that writes it and the retention."""
    op.create_table(
        "refile_report",
        sa.Column("mailbox_id", sa.String(64), sa.ForeignKey("categories.mailbox.id"), nullable=False),
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("filed", sa.Integer, nullable=False),
        sa.Column("checked", sa.Integer, nullable=False),
        sa.Column("refiled", sa.Integer, nullable=False),
        sa.Column("in_other", sa.Integer, nullable=False),
        sa.Column("gone", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("mailbox_id", "id", name="pk_refile_report"),
        sa.CheckConstraint(
            "filed >= 0 AND checked >= 0 AND refiled >= 0 AND in_other >= 0 AND gone >= 0 "
            "AND checked <= filed AND refiled <= checked AND in_other <= checked AND gone <= checked",
            name="ck_refile_report_counts",
        ),
        schema=_SCHEMA,
    )
    op.create_index("ix_refile_report_at", "refile_report", ["mailbox_id", "at"], schema=_SCHEMA)
    op.execute(_RECORD)
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION} FROM PUBLIC")
    op.execute(f"ALTER FUNCTION {_FUNCTION} OWNER TO categories_definer")
    _replace_purge(_purge_with_report().replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))


def downgrade() -> None:
    """Remove what upgrade made; the purge of revision 0015 comes back."""
    _replace_purge(_purge_before().replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute(f"DROP FUNCTION {_FUNCTION}")
    op.drop_index("ix_refile_report_at", table_name="refile_report", schema=_SCHEMA)
    op.drop_table("refile_report", schema=_SCHEMA)
