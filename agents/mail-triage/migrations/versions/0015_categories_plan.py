"""Mail categories, plan half (INT-004, ADR-0046, ADR-0047): plans, items, decisions, approvals and the apply audit.

Upgrade: ``plan`` (a partial unique index allows one open plan per mailbox), ``plan_item``, ``plan_decision``,
``plan_approval``, ``apply_audit`` and ``move_back_request``, with the guard that keeps a plan's state moves equal to
``app.core.resort_plan``. The decision functions come in the same revision (see below). Rights are in
``app/db/grants.sql``; nothing is granted here.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_SCHEMA = "categories"
_TZ = sa.DateTime(timezone=True)
_NOW = sa.text("now()")
_PLAN_STATES = "('building', 'ready', 'scheduled', 'applying', 'applied', 'replaced', 'discarded', 'cancelled')"
_ITEM_STATES = "('pending', 'approved', 'rejected', 'applied', 'skipped', 'failed')"
_CHANNELS = "('telegram', 'web', 'operator')"


def _mailbox() -> sa.Column[str]:
    """The mailbox id of ADR-0043: first column of every key."""
    return sa.Column("mailbox_id", sa.String(64), sa.ForeignKey("categories.mailbox.id"), nullable=False)


def _create_plan_tables() -> None:
    op.create_table(
        "plan",
        _mailbox(),
        sa.Column("id", sa.Uuid, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("list_version", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="building"),
        sa.Column("apply_after", _TZ),
        sa.Column("build_cursor", sa.Text),
        sa.Column("checked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cap", sa.Integer, nullable=False, server_default="5000"),
        sa.Column("unclear_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", _TZ, nullable=False, server_default=_NOW),
        sa.Column("last_activity_at", _TZ, nullable=False, server_default=_NOW),
        sa.Column("terminal_at", _TZ),
        sa.PrimaryKeyConstraint("mailbox_id", "id", name="pk_plan"),
        sa.CheckConstraint(f"state IN {_PLAN_STATES}", name="ck_plan_state"),
        sa.CheckConstraint("checked_count >= 0 AND cap >= 1 AND unclear_count >= 0", name="ck_plan_counts"),
        schema=_SCHEMA,
    )
    # One open plan per mailbox (ADR-0046): a second build waits until the first is terminal.
    op.create_index(
        "uq_plan_one_open",
        "plan",
        ["mailbox_id"],
        unique=True,
        schema=_SCHEMA,
        postgresql_where=sa.text("state NOT IN ('applied', 'replaced', 'discarded', 'cancelled')"),
    )
    op.create_table(
        "plan_item",
        sa.Column("mailbox_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.Uuid, nullable=False),
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("sender_name", sa.Text, nullable=False),
        sa.Column("sender_address", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        # The nil UUID stands for the built-in "Other"; the categories are those of the plan's list version.
        sa.Column("old_category_id", sa.Uuid, nullable=False),
        sa.Column("new_category_id", sa.Uuid, nullable=False),
        sa.Column("decision", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(64)),
        sa.Column("decided_at", _TZ),
        sa.PrimaryKeyConstraint("mailbox_id", "plan_id", "id", name="pk_plan_item"),
        sa.ForeignKeyConstraint(
            ["mailbox_id", "plan_id"],
            ["categories.plan.mailbox_id", "categories.plan.id"],
            name="fk_plan_item_plan",
        ),
        sa.UniqueConstraint("mailbox_id", "plan_id", "message_id", name="uq_plan_item_message"),
        sa.CheckConstraint("char_length(subject) <= 120", name="ck_plan_item_subject"),
        sa.CheckConstraint("decision IN ('pending', 'approved', 'rejected')", name="ck_plan_item_decision"),
        sa.CheckConstraint(f"state IN {_ITEM_STATES}", name="ck_plan_item_state"),
        # An item that was moved, skipped or failed was approved; the agent cannot invent an approval.
        sa.CheckConstraint(
            "state NOT IN ('applied', 'skipped', 'failed') OR decision = 'approved'", name="ck_plan_item_applied"
        ),
        sa.CheckConstraint("state NOT IN ('approved', 'rejected') OR state = decision", name="ck_plan_item_decided"),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_plan_item_group",
        "plan_item",
        ["mailbox_id", "plan_id", "old_category_id", "new_category_id"],
        schema=_SCHEMA,
    )


def _create_audit_tables() -> None:
    # No foreign keys to plan below: these rows live a year, the plan 14 days after it ended.
    op.create_table(
        "plan_decision",
        _mailbox(),
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("plan_id", sa.Uuid, nullable=False),
        sa.Column("scope", sa.String(8), nullable=False),
        sa.Column("item_count", sa.Integer, nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("actor_digest", sa.CHAR(64), nullable=False),
        sa.Column("at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "id", name="pk_plan_decision"),
        sa.CheckConstraint("scope IN ('group', 'ids', 'all')", name="ck_plan_decision_scope"),
        sa.CheckConstraint(f"channel IN {_CHANNELS}", name="ck_plan_decision_channel"),
        schema=_SCHEMA,
    )
    op.create_table(
        "plan_approval",
        _mailbox(),
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("plan_id", sa.Uuid, nullable=False),
        sa.Column("approved_count", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("actor_digest", sa.CHAR(64), nullable=False),
        sa.Column("at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "id", name="pk_plan_approval"),
        sa.CheckConstraint("approved_count >= 0", name="ck_plan_approval_count"),
        sa.CheckConstraint(f"channel IN {_CHANNELS}", name="ck_plan_approval_channel"),
        schema=_SCHEMA,
    )
    op.create_index("ix_plan_approval_at", "plan_approval", ["mailbox_id", "at"], schema=_SCHEMA)
    op.create_table(
        "apply_audit",
        _mailbox(),
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("plan_id", sa.Uuid, nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("old_label", sa.Text, nullable=False),
        sa.Column("new_label", sa.Text, nullable=False),
        # The channel is the one the move was approved or requested through; the actor is the writing login.
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("actor_digest", sa.CHAR(64), nullable=False),
        sa.Column("at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "id", name="pk_apply_audit"),
        sa.CheckConstraint(f"channel IN {_CHANNELS}", name="ck_apply_audit_channel"),
        schema=_SCHEMA,
    )
    op.create_index("ix_apply_audit_plan", "apply_audit", ["mailbox_id", "plan_id"], schema=_SCHEMA)
    op.create_table(
        "move_back_request",
        _mailbox(),
        sa.Column("plan_id", sa.Uuid, nullable=False),
        sa.Column("processed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("actor_digest", sa.CHAR(64), nullable=False),
        sa.Column("at", _TZ, nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("mailbox_id", "plan_id", name="pk_move_back_request"),
        schema=_SCHEMA,
    )


# The legal moves are those of app.core.resort_plan (a test compares both). An illegal move is a 409 (ERRCODE MC409).
_PLAN_GUARD = """
CREATE FUNCTION categories.plan_state_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF (OLD.state, NEW.state) NOT IN (
        ('building', 'ready'), ('building', 'replaced'),
        ('ready', 'replaced'), ('ready', 'scheduled'), ('ready', 'discarded'),
        ('scheduled', 'cancelled'), ('scheduled', 'applying'),
        ('applying', 'cancelled'), ('applying', 'applied')) THEN
        RAISE EXCEPTION 'this plan state move is not allowed' USING ERRCODE = 'MC409';
    END IF;
    IF NEW.state IN ('applied', 'replaced', 'discarded', 'cancelled') THEN
        NEW.terminal_at := now();
    END IF;
    RETURN NEW;
END
$$
"""

# The actor and the time of an apply audit row are the database's (ADR-0030); the writer names only the channel.
_AUDIT_DERIVE = """
CREATE FUNCTION categories.apply_audit_derive() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    NEW.at := now();
    NEW.actor_digest := encode(sha256(convert_to(session_user::text, 'UTF8')), 'hex');
    RETURN NEW;
END
$$
"""

# A move-back request is for an applied plan of the same mailbox, and its actor and time are the database's. The plan
# itself is purged 14 days after it ended, so the request has no foreign key (it lives a year).
_MOVE_BACK_CHECK = """
CREATE FUNCTION categories.move_back_request_check() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM categories.plan p
                    WHERE p.mailbox_id = NEW.mailbox_id AND p.id = NEW.plan_id AND p.state = 'applied') THEN
        RAISE EXCEPTION 'only an applied plan can be moved back' USING ERRCODE = 'MC409';
    END IF;
    NEW.at := now();
    NEW.processed := false;
    NEW.actor_digest := encode(sha256(convert_to(session_user::text, 'UTF8')), 'hex');
    RETURN NEW;
END
$$
"""

# The api's only way to set a decision (ADR-0047). The plan is locked, so a decision cannot race the agent's
# compare-and-set; no SQL is built from an argument; refusals carry fixed texts and no row value. MC409 is a 409 for the
# api (state, count or id mismatch), 22023 a malformed call. The channel and the actor are the session role's.
_RECORD_DECISION = r"""
CREATE FUNCTION categories.record_decision(p_mailbox text, p_plan uuid, p_count integer, p_scope jsonb, p_decision text)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_state text;
    v_total integer;
    v_kind text;
    v_ids bigint[];
    v_from uuid;
    v_to uuid;
    v_group_count integer;
    v_changed integer;
    v_uuid text := '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$';
BEGIN
    IF p_decision IS NULL OR p_decision NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'the decision is not valid' USING ERRCODE = '22023';
    END IF;
    IF p_scope IS NULL OR jsonb_typeof(p_scope) IS DISTINCT FROM 'object'
        OR coalesce(p_scope ->> 'kind', '') NOT IN ('group', 'ids', 'all') THEN
        RAISE EXCEPTION 'the scope is not valid' USING ERRCODE = '22023';
    END IF;
    v_kind := p_scope ->> 'kind';

    SELECT p.state INTO v_state FROM categories.plan p WHERE p.mailbox_id = p_mailbox AND p.id = p_plan FOR UPDATE;
    IF NOT FOUND OR v_state <> 'ready' THEN
        RAISE EXCEPTION 'the plan is not ready' USING ERRCODE = 'MC409';
    END IF;
    SELECT count(*) INTO v_total FROM categories.plan_item i WHERE i.mailbox_id = p_mailbox AND i.plan_id = p_plan;
    IF p_count IS DISTINCT FROM v_total THEN
        RAISE EXCEPTION 'the plan has changed' USING ERRCODE = 'MC409';
    END IF;

    IF v_kind = 'ids' THEN
        IF jsonb_typeof(p_scope -> 'ids') IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'the scope is not valid' USING ERRCODE = '22023';
        END IF;
        IF jsonb_array_length(p_scope -> 'ids') > 200 THEN
            RAISE EXCEPTION 'too many ids' USING ERRCODE = 'MC409';
        END IF;
        IF jsonb_array_length(p_scope -> 'ids') = 0 OR EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_scope -> 'ids') e
             WHERE jsonb_typeof(e) <> 'number' OR (e #>> '{}') !~ '^[0-9]{1,18}$') THEN
            RAISE EXCEPTION 'the scope is not valid' USING ERRCODE = '22023';
        END IF;
        SELECT array_agg(DISTINCT (e #>> '{}')::bigint) INTO v_ids FROM jsonb_array_elements(p_scope -> 'ids') e;
        IF (SELECT count(*) FROM categories.plan_item i
             WHERE i.mailbox_id = p_mailbox AND i.plan_id = p_plan AND i.id = ANY (v_ids)) <> cardinality(v_ids) THEN
            RAISE EXCEPTION 'an id does not belong to the plan' USING ERRCODE = 'MC409';
        END IF;
    ELSIF v_kind = 'group' THEN
        IF NOT coalesce((p_scope ->> 'from') ~ v_uuid, false) OR NOT coalesce((p_scope ->> 'to') ~ v_uuid, false)
            OR jsonb_typeof(p_scope -> 'groupCount') IS DISTINCT FROM 'number'
            OR NOT coalesce((p_scope ->> 'groupCount') ~ '^[0-9]{1,9}$', false) THEN
            RAISE EXCEPTION 'the scope is not valid' USING ERRCODE = '22023';
        END IF;
        v_from := (p_scope ->> 'from')::uuid;
        v_to := (p_scope ->> 'to')::uuid;
        v_group_count := (p_scope ->> 'groupCount')::integer;
        IF (SELECT count(*) FROM categories.plan_item i
             WHERE i.mailbox_id = p_mailbox AND i.plan_id = p_plan
               AND i.old_category_id = v_from AND i.new_category_id = v_to) <> v_group_count THEN
            RAISE EXCEPTION 'the group has changed' USING ERRCODE = 'MC409';
        END IF;
    END IF;

    UPDATE categories.plan_item i
       SET decision = p_decision, state = p_decision, decided_at = now()
     WHERE i.mailbox_id = p_mailbox AND i.plan_id = p_plan AND i.state IN ('pending', 'approved', 'rejected')
       AND (v_kind = 'all'
            OR (v_kind = 'ids' AND i.id = ANY (v_ids))
            OR (v_kind = 'group' AND i.old_category_id = v_from AND i.new_category_id = v_to));
    GET DIAGNOSTICS v_changed = ROW_COUNT;

    INSERT INTO categories.plan_decision (mailbox_id, plan_id, scope, item_count, decision, channel, actor_digest, at)
    VALUES (p_mailbox, p_plan, v_kind, v_changed, p_decision,
            CASE session_user
                WHEN 'mail_triage_runtime' THEN 'telegram'
                WHEN 'web_settings_runtime' THEN 'web'
                ELSE 'operator'
            END,
            encode(sha256(convert_to(session_user::text, 'UTF8')), 'hex'), now());
    UPDATE categories.plan SET last_activity_at = now() WHERE mailbox_id = p_mailbox AND id = p_plan;
    RETURN v_changed;
END
$$
"""

_TRIGGERS = (
    "CREATE TRIGGER plan_state_guard BEFORE UPDATE OF state ON categories.plan "
    "FOR EACH ROW WHEN (OLD.state IS DISTINCT FROM NEW.state) EXECUTE FUNCTION categories.plan_state_guard()",
    "CREATE TRIGGER apply_audit_derive BEFORE INSERT ON categories.apply_audit "
    "FOR EACH ROW EXECUTE FUNCTION categories.apply_audit_derive()",
    "CREATE TRIGGER move_back_request_check BEFORE INSERT ON categories.move_back_request "
    "FOR EACH ROW EXECUTE FUNCTION categories.move_back_request_check()",
)
_FUNCTIONS = (
    "categories.plan_state_guard()",
    "categories.apply_audit_derive()",
    "categories.move_back_request_check()",
    "categories.record_decision(text, uuid, integer, jsonb, text)",
)


def upgrade() -> None:
    """Create the plan tables, the state guard and its trigger."""
    _create_plan_tables()
    _create_audit_tables()
    for function_sql in (_PLAN_GUARD, _AUDIT_DERIVE, _MOVE_BACK_CHECK, _RECORD_DECISION):
        op.execute(function_sql)
    for statement in _TRIGGERS:
        op.execute(statement)
    for function in _FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")


def downgrade() -> None:
    """Remove what upgrade made; the list half of revision 0014 stays."""
    for function in _FUNCTIONS:
        op.execute(f"DROP FUNCTION {function} CASCADE")
    for table in ("move_back_request", "apply_audit", "plan_approval", "plan_decision", "plan_item", "plan"):
        op.drop_table(table, schema=_SCHEMA)
