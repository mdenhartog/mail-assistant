"""The category checks follow the v2 limits of category-policy (INT-008, U-label-structure-31, ADR-0025, ADR-0053).

A category name is nested per segment: the whole label ``Assistant/<name>`` is at most 225 characters, so the name is at
most 215; the description is at most 1 500 characters; a list holds at most 100 categories (positions 0 to 99). The
three named checks of revision 0014 are dropped and made again with the new limits; no row is touched, and every row
within the v1 limits is within the v2 limits. The downgrade restores the v1 limits and stops, changing nothing, while a
row exceeds them.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_TABLE = "category"
_SCHEMA = "categories"

_V1 = {
    "ck_category_name_length": "char_length(name) BETWEEN 1 AND 40",
    "ck_category_description_length": "char_length(description) <= 500",
    "ck_category_position": "position BETWEEN 0 AND 49",
}
_V2 = {
    "ck_category_name_length": "char_length(name) BETWEEN 1 AND 215",
    "ck_category_description_length": "char_length(description) <= 1500",
    "ck_category_position": "position BETWEEN 0 AND 99",
}

# The rows no v1 check would accept: one count, a fixed statement.
_BEYOND_V1 = sa.text(
    "SELECT count(*) FROM categories.category "
    "WHERE NOT (char_length(name) BETWEEN 1 AND 40 AND char_length(description) <= 500 AND position BETWEEN 0 AND 49)"
)


def _replace_checks(limits: dict[str, str]) -> None:
    """Drop the three named checks and create them again with the given conditions."""
    for name, condition in limits.items():
        op.drop_constraint(name, _TABLE, schema=_SCHEMA, type_="check")
        op.create_check_constraint(name, _TABLE, condition, schema=_SCHEMA)


def upgrade() -> None:
    """Relax the name, description and position checks to the v2 limits."""
    _replace_checks(_V2)


def downgrade() -> None:
    """Restore the v1 limits; refuse, changing nothing, while a category exceeds them."""
    beyond = op.get_bind().execute(_BEYOND_V1).scalar_one()
    if beyond:
        raise RuntimeError(
            f"cannot restore the v1 category limits: {beyond} categories exceed them "
            "(name over 40, description over 500 or position over 49); they fit the v2 limits only"
        )
    _replace_checks(_V1)
