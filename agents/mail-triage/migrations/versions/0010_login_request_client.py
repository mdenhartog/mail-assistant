"""Login request client digest (INT-002, ADR-0039, RT-01, RT-04): who asked is kept as a keyed digest.

Upgrade: ``web_auth.login_request`` gains ``client_hash`` (CHAR(64), NOT NULL, no default). It holds the keyed digest of
the client key, never an address. Rows that exist at upgrade time (an hour old at most) get 64 zeros: no client, so no
client limit ever matches them.
Grants (``app/db/grants.sql``): the web role reads and inserts the column; it may only UPDATE ``attempts``, ``sent_at``
and ``dead_at`` of a login request, so a request cannot change who asked. The agent role has no access to the table.

Downgrade: the column goes. Login requests stay.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"  # 0009 is the head on main
branch_labels = None
depends_on = None

_NO_CLIENT = "0" * 64


def upgrade() -> None:
    """Add the column with a stop-gap value for the rows that exist, then take the default away."""
    op.add_column(
        "login_request",
        sa.Column("client_hash", sa.CHAR(64), nullable=False, server_default=_NO_CLIENT),
        schema="web_auth",
    )
    op.alter_column("login_request", "client_hash", server_default=None, schema="web_auth")


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("login_request", "client_hash", schema="web_auth")
