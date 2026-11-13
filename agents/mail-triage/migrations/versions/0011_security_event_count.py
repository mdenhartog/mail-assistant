"""Security event count and client digest (INT-002, ADR-0039, SEC-04, SEC-09): wrong codes are counted, not hidden.

Upgrade:
- ``web_auth.security_event`` gains ``count`` (INTEGER, NOT NULL, default 1). A repeat of a counted kind in one
  ``(kind, client_key, window)`` raises it instead of being dropped, so the wrong-code alert can add them up.
- ``client_key`` now holds the keyed digest of the client (the web app writes it), never the address. The rows that
  exist at upgrade time hold a clear address and the migration has no key, so it cannot make that digest. It replaces
  each value with the SHA-256 of ``legacy:<row id>``: 64 hex characters, unique per row (the unique constraint of kind,
  client and window keeps holding), tied to no client. The kind, time, result and count of the rows stay.
Grants (``app/db/grants.sql``): the web role may additionally UPDATE the column ``count`` and nothing else; the agent
role gets no access here (the alert of U-48 grants its own read).

Downgrade: ``count`` goes (the counts with it). A digest cannot be turned back into an address, so ``client_key`` keeps
its digests, which the older code reads as opaque keys.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_UNLINK = (
    "UPDATE web_auth.security_event SET client_key = encode(sha256(convert_to('legacy:' || id::text, 'UTF8')), 'hex')"
)


def upgrade() -> None:
    """Add the count, then take the clear addresses off the rows that exist."""
    op.add_column(
        "security_event",
        sa.Column("count", sa.Integer, nullable=False, server_default="1"),
        schema="web_auth",
    )
    op.execute(_UNLINK)


def downgrade() -> None:
    """Drop the count; the digests stay."""
    op.drop_column("security_event", "count", schema="web_auth")
