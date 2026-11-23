"""The sort-again request, the two plan kinds and the system approval (INT-008, U-label-structure-20, ADR-0056).

Expand only: every new column has a default or is nullable, so the running agent keeps working until the units that
use them land. An old plan reads as a ``review`` plan without a request or a threshold.

- ``resort_request``: insert-only record of "Sort everything again" (threshold 50 to 100; the actor digest, the channel
  and the time are the database's). ``request_resort(mailbox, threshold)`` is the api's only way to write it; it refuses
  a threshold that is not a whole number from 50 to 100 and a mailbox that has an open plan.
- ``plan.kind`` (``auto`` or ``review``), ``plan.request_id`` and ``plan.threshold``: the threshold is copied from the
  request when the plan is inserted and never changes (a trigger refuses any change of the three, for every role). The
  partial unique index now allows one open plan per mailbox **and kind**.
- ``plan_item``: the old and the new pair, ``confidence_pct``, ``decision_source`` (``user`` or ``threshold``) and
  ``tip``.
- ``approve_system_plan(plan)``: the agent's own approval of an ``auto`` plan. It locks the plan, re-checks every item
  against the stored threshold, records the decision source ``threshold``, inserts the approval that counts toward the
  rolling 24 hours and always schedules the plan after the configured delay (at least a minute), so the notice with
  Cancel, Move back and Lock is sent first, whatever the 24-hour sum. The approval is recorded with the channel
  ``system`` (``plan_approval`` and ``apply_audit`` accept it; the apply copies it to its audit rows). Rights are in
  ``app/db/grants.sql``: the api has no right on it.
- ``record_decision`` and ``approve_plan`` (revision 0015, callable by the api) now act only on a ``review`` plan.
- ``purge_expired()`` removes requests after a year (when no plan still points at them).

The two new functions are ``SECURITY DEFINER``, owned by the non-login definer role, with the search path pinned and no
right for ``PUBLIC``. The downgrade removes what this revision added, restores the index and the function bodies of
revision 0015 and the old channel checks (``system`` rows become ``telegram``); it stops with a database error
when a mailbox has an ``auto`` and a ``review`` plan open at once (the old index allows one).

Revision ID: 0029
Revises: 0028
"""

# ruff: noqa: S608  # fixed DDL text, never built from input

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_SCHEMA = "categories"
_TZ = sa.DateTime(timezone=True)
_PURGE = "categories.purge_expired()"
_OPEN = "state NOT IN ('applied', 'replaced', 'discarded', 'cancelled')"
_CHANNEL = """CASE session_user
                WHEN 'mail_triage_runtime' THEN 'telegram'
                WHEN 'web_settings_runtime' THEN 'web'
                ELSE 'operator'
            END"""
_SYSTEM_CHANNELS = "('telegram', 'web', 'operator', 'system')"
_OLD_CHANNELS = "('telegram', 'web', 'operator')"
_CHANNEL_CHECKS = (("plan_approval", "ck_plan_approval_channel"), ("apply_audit", "ck_apply_audit_channel"))
_ACTOR = "encode(sha256(convert_to(session_user::text, 'UTF8')), 'hex')"

_REQUEST_DERIVE = f"""
CREATE FUNCTION categories.resort_request_derive() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    NEW.at := now();
    NEW.channel := {_CHANNEL};
    NEW.actor_digest := {_ACTOR};
    RETURN NEW;
END
$$
"""

# The plan copies the threshold of its request and nobody can pick another one (not even the agent that inserts it).
_PLAN_REQUEST_COPY = """
CREATE FUNCTION categories.plan_request_copy() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NEW.request_id IS NULL THEN
        NEW.threshold := NULL;
        RETURN NEW;
    END IF;
    SELECT r.threshold INTO NEW.threshold FROM categories.resort_request r
     WHERE r.mailbox_id = NEW.mailbox_id AND r.id = NEW.request_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'the request of this plan is not known' USING ERRCODE = 'MC409';
    END IF;
    RETURN NEW;
END
$$
"""

_PLAN_IMMUTABLE = """
CREATE FUNCTION categories.plan_request_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    RAISE EXCEPTION 'the kind, the request and the threshold of a plan never change' USING ERRCODE = 'MC409';
END
$$
"""

# The api's only write path to resort_request (ADR-0056). The threshold is numeric so that a fraction reaches the
# function and is refused here with a fixed text, whatever the caller's driver does with it.
_REQUEST_RESORT = """
CREATE FUNCTION categories.request_resort(p_mailbox text, p_threshold numeric) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_id uuid;
BEGIN
    IF p_threshold IS NULL OR p_threshold < 50 OR p_threshold > 100 OR p_threshold <> trunc(p_threshold) THEN
        RAISE EXCEPTION 'the threshold must be a whole number from 50 to 100' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT 1 FROM categories.plan p
                WHERE p.mailbox_id = p_mailbox AND p.kind IN ('auto', 'review')
                  AND p.state NOT IN ('applied', 'replaced', 'discarded', 'cancelled')) THEN
        RAISE EXCEPTION 'a plan is already open' USING ERRCODE = 'MC409';
    END IF;
    INSERT INTO categories.resort_request (mailbox_id, threshold)
    VALUES (p_mailbox, p_threshold::integer) RETURNING id INTO v_id;
    RETURN v_id;
END
$$
"""

# The agent's approval of an ``auto`` plan (ADR-0056, ADR-0047). One locked transaction: every item is checked against
# the threshold stored on the plan (a missing confidence never qualifies), the items become approved with the source
# ``threshold``, the approval is recorded with the channel ``system`` (a constant, not the session's role) and counts
# toward the 24-hour sum that approve_plan takes for a user. The plan is
# always scheduled for now plus the delay (at least a minute): the notice must reach the user before any move, whatever
# the sum. The function takes no threshold, no delay and no mailbox; a repeated call on a scheduled plan returns it.
_APPROVE_SYSTEM_PLAN = f"""
CREATE FUNCTION categories.approve_system_plan(p_plan uuid)
RETURNS TABLE (state text, apply_after timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
#variable_conflict use_column
DECLARE
    v_mailbox text;
    v_kind text;
    v_state text;
    v_after timestamptz;
    v_threshold integer;
    v_approved integer;
    v_delay integer;
BEGIN
    SELECT p.mailbox_id, p.kind, p.state, p.apply_after, p.threshold
      INTO v_mailbox, v_kind, v_state, v_after, v_threshold
      FROM categories.plan p WHERE p.id = p_plan FOR UPDATE;
    IF NOT FOUND OR v_kind <> 'auto' THEN
        RAISE EXCEPTION 'the plan is not a system plan' USING ERRCODE = 'MC409';
    END IF;
    IF v_state = 'scheduled' THEN
        RETURN QUERY SELECT v_state, v_after;
        RETURN;
    END IF;
    IF v_state <> 'ready' OR v_threshold IS NULL THEN
        RAISE EXCEPTION 'the plan is not ready' USING ERRCODE = 'MC409';
    END IF;
    IF EXISTS (SELECT 1 FROM categories.plan_item i
                WHERE i.mailbox_id = v_mailbox AND i.plan_id = p_plan
                  AND (i.confidence_pct IS NULL OR i.confidence_pct < v_threshold)) THEN
        RAISE EXCEPTION 'an item is below the threshold of the plan' USING ERRCODE = 'MC409';
    END IF;
    SELECT c.delay_minutes INTO v_delay
      FROM categories.apply_config c WHERE c.mailbox_id = v_mailbox;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'the apply settings are not ready' USING ERRCODE = 'MC409';
    END IF;

    UPDATE categories.plan_item i
       SET decision = 'approved', state = 'approved', decision_source = 'threshold', decided_at = now()
     WHERE i.mailbox_id = v_mailbox AND i.plan_id = p_plan AND i.decision = 'pending';
    SELECT count(*) INTO v_approved
      FROM categories.plan_item i WHERE i.mailbox_id = v_mailbox AND i.plan_id = p_plan AND i.decision = 'approved';
    INSERT INTO categories.plan_approval (mailbox_id, plan_id, approved_count, channel, actor_digest, at)
    VALUES (v_mailbox, p_plan, v_approved, 'system', {_ACTOR}, now());
    v_after := now() + make_interval(mins => greatest(v_delay, 1));
    UPDATE categories.plan p SET state = 'scheduled', apply_after = v_after, last_activity_at = now()
     WHERE p.mailbox_id = v_mailbox AND p.id = p_plan;
    RETURN QUERY SELECT 'scheduled'::text, v_after;
END
$$
"""

_TRIGGERS = (
    ("resort_request_derive", "BEFORE INSERT ON categories.resort_request", "categories.resort_request_derive()", ""),
    ("plan_request_copy", "BEFORE INSERT ON categories.plan", "categories.plan_request_copy()", ""),
    (
        "plan_request_immutable",
        "BEFORE UPDATE OF kind, request_id, threshold ON categories.plan",
        "categories.plan_request_immutable()",
        "WHEN (OLD.kind IS DISTINCT FROM NEW.kind OR OLD.request_id IS DISTINCT FROM NEW.request_id "
        "OR OLD.threshold IS DISTINCT FROM NEW.threshold) ",
    ),
)
_FUNCTIONS = (
    "categories.resort_request_derive()",
    "categories.plan_request_copy()",
    "categories.plan_request_immutable()",
    "categories.request_resort(text, numeric)",
    "categories.approve_system_plan(uuid)",
)

_PURGE_PART = """    DELETE FROM categories.resort_request r WHERE r.at < pg_catalog.now() - interval '1 year'
       AND NOT EXISTS (SELECT 1 FROM categories.plan p WHERE p.mailbox_id = r.mailbox_id AND p.request_id = r.id);
    GET DIAGNOSTICS n = ROW_COUNT;
    removed := removed || jsonb_build_object('resort_request', n);
"""
_PURGE_MARK = "    -- A rejection lives until the list changes again.\n"


def _replace_purge(sql: str) -> None:
    # Only the owner of a function may replace it: take it back for the statement, then hand it over again.
    op.execute(f"ALTER FUNCTION {_PURGE} OWNER TO current_user")
    op.execute(sql)
    op.execute(f"ALTER FUNCTION {_PURGE} OWNER TO categories_definer")


_LOOKUP = "FROM categories.plan p WHERE p.mailbox_id = p_mailbox AND p.id = p_plan FOR UPDATE;"
_REVIEW_LOOKUP = (
    "FROM categories.plan p WHERE p.mailbox_id = p_mailbox AND p.id = p_plan AND p.kind = 'review' FOR UPDATE;"
)
_USER_FUNCTIONS = (
    "categories.record_decision(text, uuid, integer, jsonb, text)",
    "categories.approve_plan(text, uuid, integer)",
)


def _replace_user_functions(old: str, new: str) -> None:
    """Rebuild the api's two plan functions from their definitions in the database, with ``old`` swapped for ``new``."""
    for function in _USER_FUNCTIONS:
        body = _current_definition(function)
        if body.count(old) != 1:
            raise RuntimeError("a plan function has changed shape")
        op.execute(f"ALTER FUNCTION {function} OWNER TO current_user")
        op.execute(body.replace(old, new, 1))
        op.execute(f"ALTER FUNCTION {function} OWNER TO categories_definer")


def _set_channels(allowed: str) -> None:
    for table, name in _CHANNEL_CHECKS:
        op.drop_constraint(name, table, schema=_SCHEMA)
        op.create_check_constraint(name, table, f"channel IN {allowed}", schema=_SCHEMA)


def _remove_system_channel() -> None:
    """The old constraints know no system channel; the rows that carry it were the agent's own login (telegram)."""
    for table, _name in _CHANNEL_CHECKS:
        op.execute(f"UPDATE categories.{table} SET channel = 'telegram' WHERE channel = 'system'")
    _set_channels(_OLD_CHANNELS)


def _current_definition(function: str) -> str:
    statement = sa.text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))")
    return str(op.get_bind().execute(statement, {"name": function}).scalar_one())


def _current_purge() -> str:
    """The definition in the database now, so this revision builds on whatever the chain made of it."""
    return _current_definition(_PURGE)


def _create_request_table() -> None:
    op.create_table(
        "resort_request",
        sa.Column("mailbox_id", sa.String(64), sa.ForeignKey("categories.mailbox.id"), nullable=False),
        sa.Column("id", sa.Uuid, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("threshold", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(16), nullable=False, server_default="operator"),
        sa.Column("actor_digest", sa.CHAR(64), nullable=False, server_default=sa.text("repeat('0', 64)")),
        sa.Column("at", _TZ, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("mailbox_id", "id", name="pk_resort_request"),
        sa.CheckConstraint("threshold BETWEEN 50 AND 100", name="ck_resort_request_threshold"),
        sa.CheckConstraint("channel IN ('telegram', 'web', 'operator')", name="ck_resort_request_channel"),
        schema=_SCHEMA,
    )
    op.create_index("ix_resort_request_at", "resort_request", ["mailbox_id", "at"], schema=_SCHEMA)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON categories.resort_request TO categories_definer")


def _expand_plan_tables() -> None:
    op.add_column("plan", sa.Column("kind", sa.String(8), nullable=False, server_default="review"), schema=_SCHEMA)
    op.add_column("plan", sa.Column("request_id", sa.Uuid), schema=_SCHEMA)
    op.add_column("plan", sa.Column("threshold", sa.Integer), schema=_SCHEMA)
    op.create_check_constraint("ck_plan_kind", "plan", "kind IN ('auto', 'review')", schema=_SCHEMA)
    op.create_check_constraint(
        "ck_plan_request",
        "plan",
        "kind = 'review' OR (request_id IS NOT NULL AND threshold IS NOT NULL)",
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_plan_threshold", "plan", "threshold IS NULL OR threshold BETWEEN 50 AND 100", schema=_SCHEMA
    )
    op.create_foreign_key(
        "fk_plan_request",
        "plan",
        "resort_request",
        ["mailbox_id", "request_id"],
        ["mailbox_id", "id"],
        source_schema=_SCHEMA,
        referent_schema=_SCHEMA,
    )
    op.drop_index("uq_plan_one_open", table_name="plan", schema=_SCHEMA)
    op.create_index(
        "uq_plan_one_open", "plan", ["mailbox_id", "kind"], unique=True, schema=_SCHEMA, postgresql_where=sa.text(_OPEN)
    )

    for column in ("old_topic_id", "old_extra_id", "new_topic_id", "new_extra_id"):
        op.add_column("plan_item", sa.Column(column, sa.Uuid), schema=_SCHEMA)
    op.add_column("plan_item", sa.Column("confidence_pct", sa.Integer), schema=_SCHEMA)
    op.add_column(
        "plan_item", sa.Column("decision_source", sa.String(16), nullable=False, server_default="user"), schema=_SCHEMA
    )
    op.add_column("plan_item", sa.Column("tip", sa.Text), schema=_SCHEMA)
    op.create_check_constraint(
        "ck_plan_item_confidence",
        "plan_item",
        "confidence_pct IS NULL OR confidence_pct BETWEEN 0 AND 100",
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_plan_item_decision_source", "plan_item", "decision_source IN ('user', 'threshold')", schema=_SCHEMA
    )
    op.create_check_constraint(
        "ck_plan_item_threshold_approved",
        "plan_item",
        "decision_source <> 'threshold' OR decision = 'approved'",
        schema=_SCHEMA,
    )
    op.create_check_constraint("ck_plan_item_tip", "plan_item", "char_length(tip) <= 500", schema=_SCHEMA)


def upgrade() -> None:
    """Create the request table, expand the plan tables, then the triggers, the two functions and the retention."""
    _create_request_table()
    _expand_plan_tables()
    for function_sql in (
        _REQUEST_DERIVE,
        _PLAN_REQUEST_COPY,
        _PLAN_IMMUTABLE,
        _REQUEST_RESORT,
        _APPROVE_SYSTEM_PLAN,
    ):
        op.execute(function_sql)
    for name, when, function, condition in _TRIGGERS:
        op.execute(f"CREATE TRIGGER {name} {when} FOR EACH ROW {condition}EXECUTE FUNCTION {function}")
    for function in _FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
        op.execute(f"ALTER FUNCTION {function} OWNER TO categories_definer")
    _set_channels(_SYSTEM_CHANNELS)
    _replace_user_functions(_LOOKUP, _REVIEW_LOOKUP)
    body = _current_purge()
    if body.count(_PURGE_MARK) != 1:
        raise RuntimeError("the purge function has changed shape")
    _replace_purge(body.replace(_PURGE_MARK, _PURGE_PART + _PURGE_MARK, 1))


def downgrade() -> None:
    """Remove what upgrade made and put the one-open-plan index of revision 0015 back."""
    body = _current_purge()
    if _PURGE_PART not in body:
        raise RuntimeError("the purge function does not hold the part of revision 0029")
    _replace_purge(body.replace(_PURGE_PART, "", 1))
    _replace_user_functions(_REVIEW_LOOKUP, _LOOKUP)
    _remove_system_channel()
    for name, _when, _function, _condition in reversed(_TRIGGERS):
        table = "resort_request" if name == "resort_request_derive" else "plan"
        op.execute(f"DROP TRIGGER {name} ON categories.{table}")
    for function in reversed(_FUNCTIONS):
        op.execute(f"DROP FUNCTION {function}")

    for constraint in ("ck_plan_item_tip", "ck_plan_item_threshold_approved", "ck_plan_item_decision_source"):
        op.drop_constraint(constraint, "plan_item", schema=_SCHEMA)
    op.drop_constraint("ck_plan_item_confidence", "plan_item", schema=_SCHEMA)
    for column in ("tip", "decision_source", "confidence_pct", "new_extra_id", "new_topic_id", "old_extra_id"):
        op.drop_column("plan_item", column, schema=_SCHEMA)
    op.drop_column("plan_item", "old_topic_id", schema=_SCHEMA)

    op.drop_index("uq_plan_one_open", table_name="plan", schema=_SCHEMA)
    op.create_index(
        "uq_plan_one_open", "plan", ["mailbox_id"], unique=True, schema=_SCHEMA, postgresql_where=sa.text(_OPEN)
    )
    op.drop_constraint("fk_plan_request", "plan", schema=_SCHEMA, type_="foreignkey")
    for constraint in ("ck_plan_threshold", "ck_plan_request", "ck_plan_kind"):
        op.drop_constraint(constraint, "plan", schema=_SCHEMA)
    for column in ("threshold", "request_id", "kind"):
        op.drop_column("plan", column, schema=_SCHEMA)

    op.drop_index("ix_resort_request_at", table_name="resort_request", schema=_SCHEMA)
    op.drop_table("resort_request", schema=_SCHEMA)
