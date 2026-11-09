"""Drop ``alert.awaiting_input``: an open question lives in the single conversation row (ADR-0026).

Upgrade: the most recently updated alert with a known open question is copied to the ``conversation`` row (unless a
dialogue is already pending there, which is newer and wins), then the column is dropped. Open questions have no expiry,
so the row stores the far-future ``NO_EXPIRY`` moment; the nonce is random
(two UUIDs as hex, 64 characters).

Downgrade (best effort): the column returns, nullable. A pending snooze or reply question is copied back to its alert;
the conversation row is left as it is, so upgrading again changes nothing. Settings dialogues have no alert and are not
copied. A question for an alert that no longer exists is not restored.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Same mapping as app/db/pg_store.py: snooze_hours -> (snooze, hours), reply_text -> (reply, text).
# 9999-12-31 UTC is app.db.pg_conversation.NO_EXPIRY; the migration keeps its own copy so it never changes with the app.
_MOVE_UP = """
INSERT INTO conversation (id, kind, target, step, partial, nonce, expires_at)
SELECT 1,
       CASE awaiting_input WHEN 'snooze_hours' THEN 'snooze' ELSE 'reply' END,
       id::text,
       CASE awaiting_input WHEN 'snooze_hours' THEN 'hours' ELSE 'text' END,
       '{}'::jsonb,
       replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
       TIMESTAMPTZ '9999-12-31 00:00:00+00'
FROM alert
WHERE awaiting_input IN ('snooze_hours', 'reply_text')
ORDER BY updated_at DESC, id DESC
LIMIT 1
ON CONFLICT (id) DO NOTHING
"""

_MOVE_DOWN = """
UPDATE alert SET awaiting_input = CASE conversation.kind WHEN 'snooze' THEN 'snooze_hours' ELSE 'reply_text' END
FROM conversation
WHERE conversation.kind IN ('snooze', 'reply') AND alert.id::text = conversation.target
"""


def upgrade() -> None:
    """Move the open question, then drop the column."""
    op.execute(_MOVE_UP)
    op.drop_column("alert", "awaiting_input")


def downgrade() -> None:
    """Add the column back and put a pending snooze or reply question on its alert."""
    op.add_column("alert", sa.Column("awaiting_input", sa.String(16)))
    op.execute(_MOVE_DOWN)
