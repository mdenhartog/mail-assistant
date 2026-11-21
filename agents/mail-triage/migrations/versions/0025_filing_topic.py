"""The filing code switch, contract half (INT-008, U-label-structure-32, ADR-0053 decision 2).

The agent now reads and writes ``filing.topic_id`` only, so this revision drops ``filing.category_id``, the bridge
trigger ``filing_topic_bridge`` and its function (all added or kept by revision 0024). Every row keeps its
``topic_id``. The downgrade restores the column (copied from ``topic_id``), the function and the trigger, so the
code of the previous release works again. Rights are in ``app/db/grants.sql``; nothing is granted here.

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

_SCHEMA = "categories"

# The same function and trigger as revision 0024 made: the topic follows the category until this revision's upgrade.
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


def upgrade() -> None:
    """Drop the bridge and ``category_id``; ``topic_id`` already holds every value."""
    op.execute("DROP TRIGGER filing_topic_bridge ON categories.filing")
    op.execute("DROP FUNCTION categories.filing_topic_bridge()")
    op.drop_column("filing", "category_id", schema=_SCHEMA)


def downgrade() -> None:
    """Bring back ``category_id`` (copied from ``topic_id``), the function and the trigger."""
    op.add_column("filing", sa.Column("category_id", sa.Uuid), schema=_SCHEMA)
    op.execute("UPDATE categories.filing SET category_id = topic_id")
    op.alter_column("filing", "category_id", nullable=False, schema=_SCHEMA)
    op.execute(_BRIDGE_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION categories.filing_topic_bridge() FROM PUBLIC")
    op.execute("ALTER FUNCTION categories.filing_topic_bridge() OWNER TO categories_definer")
    op.execute(_BRIDGE_TRIGGER)
