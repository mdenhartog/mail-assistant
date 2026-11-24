"""The label boundary, expand step (INT-010, U-label-prefix-removal-02, ADR-0060, ADR-0061).

Expand only: nothing is dropped, every new column has a default, so the running agent keeps working until the units
that use the new objects land. ``category_label``, ``gmail_label`` and ``adoptable`` go in a later revision.

New tables in schema ``categories`` (every key starts with ``mailbox_id``):

- ``managed_label(label_id, role category|other|archive, category_id, label_name)``: the Gmail labels the agent may
  change, by id. Filled from ``category_label``; "other" and the archive label are written by the agent once their ids
  are known.
- ``label_migration(state pending|confirmed|done, plan_hash)``: gates every label write. ``pending`` when a label
  named ``Assistant/...`` is known (``category_label`` or ``gmail_label``), else ``done``. Only the confirmation
  function moves ``pending`` to ``confirmed`` (a trigger refuses any other writer); ``confirmed`` goes to ``done``.
- ``label_rename_item(label_id, old_name, new_name, mail_count, action rename|merge, state)``: the plan, and the
  backup of the old names that a restore reads.
- ``label_empty_since(label_id, empty_since, last_seen_empty)``: the persistent timers of the delayed delete.
- ``deleted_label(label_id_hash, name, deleted_at)``: the record the page shows as "recently deleted".
- ``label_confirmation`` and ``label_restore_request``: insert-only records written through the two functions below.

Settings: ``settings.schedule`` gets ``label_wait_minutes`` (5 to 720, default 720), ``label_protection_days`` (1 to 30,
default 7) and ``label_retention_days`` (7 to 90, default 30), bounds of ``category_policy.settings``.
``categories.list_settings`` gets ``other_label`` (default ``Other``); the default of ``archive_label`` becomes
``Archive`` for new rows, existing rows are not touched. The revision inserts no list version.

Functions (``SECURITY DEFINER``, owned by ``categories_definer``, search path pinned, nothing for ``PUBLIC``):

- ``label_plan_hash(mailbox)``: sha256 (hex) of the text of the jsonb array of ``[label_id, old_name, new_name]`` in
  ``label_id`` order (collation C). The agent stores it in ``label_migration.plan_hash`` when the plan is complete.
- ``confirm_label_rename(mailbox, plan_hash, skipped_ids)`` (the api): refuses unless the hash equals the stored hash
  and the hash of the items now; inserts the confirmation and moves the state to ``confirmed``. A repeat with the same
  arguments returns the same id and writes nothing.
- ``request_label_restore(mailbox)`` (the api): needs a confirmed or done plan; one open request per mailbox.

The whole revision is idempotent (``IF NOT EXISTS``, ``ON CONFLICT DO NOTHING``, ``CREATE OR REPLACE``): a rerun after
a crash completes the data and changes nothing that is complete. The downgrade removes every new object.

Revision ID: 0030
Revises: 0029
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS categories.managed_label (
        mailbox_id varchar(64) NOT NULL,
        label_id text NOT NULL,
        role varchar(16) NOT NULL,
        category_id uuid,
        label_name text NOT NULL,
        CONSTRAINT pk_managed_label PRIMARY KEY (mailbox_id, label_id),
        CONSTRAINT uq_managed_label_category UNIQUE (mailbox_id, category_id),
        CONSTRAINT fk_managed_label_mailbox FOREIGN KEY (mailbox_id) REFERENCES categories.mailbox (id),
        CONSTRAINT fk_managed_label_identity FOREIGN KEY (mailbox_id, category_id)
            REFERENCES categories.category_identity (mailbox_id, id),
        CONSTRAINT ck_managed_label_role CHECK (role IN ('category', 'other', 'archive')),
        CONSTRAINT ck_managed_label_category CHECK ((role = 'category') = (category_id IS NOT NULL))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_managed_label_role ON categories.managed_label (mailbox_id, role)"
    " WHERE role <> 'category'",
    """
    CREATE TABLE IF NOT EXISTS categories.label_migration (
        mailbox_id varchar(64) NOT NULL,
        state varchar(12) NOT NULL,
        plan_hash char(64),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT pk_label_migration PRIMARY KEY (mailbox_id),
        CONSTRAINT fk_label_migration_mailbox FOREIGN KEY (mailbox_id) REFERENCES categories.mailbox (id),
        CONSTRAINT ck_label_migration_state CHECK (state IN ('pending', 'confirmed', 'done'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories.label_rename_item (
        mailbox_id varchar(64) NOT NULL,
        label_id text NOT NULL,
        old_name text NOT NULL,
        new_name text NOT NULL,
        mail_count integer NOT NULL DEFAULT 0,
        action varchar(8) NOT NULL,
        state varchar(8) NOT NULL DEFAULT 'planned',
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT pk_label_rename_item PRIMARY KEY (mailbox_id, label_id),
        CONSTRAINT fk_label_rename_item_mailbox FOREIGN KEY (mailbox_id) REFERENCES categories.mailbox (id),
        CONSTRAINT ck_label_rename_item_action CHECK (action IN ('rename', 'merge')),
        CONSTRAINT ck_label_rename_item_state CHECK (state IN ('planned', 'skipped', 'done', 'kept')),
        CONSTRAINT ck_label_rename_item_count CHECK (mail_count >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories.label_empty_since (
        mailbox_id varchar(64) NOT NULL,
        label_id text NOT NULL,
        empty_since timestamptz NOT NULL,
        last_seen_empty timestamptz NOT NULL,
        CONSTRAINT pk_label_empty_since PRIMARY KEY (mailbox_id, label_id),
        CONSTRAINT fk_label_empty_since_mailbox FOREIGN KEY (mailbox_id) REFERENCES categories.mailbox (id),
        CONSTRAINT ck_label_empty_since_order CHECK (last_seen_empty >= empty_since)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories.deleted_label (
        mailbox_id varchar(64) NOT NULL,
        label_id_hash char(64) NOT NULL,
        name text NOT NULL,
        deleted_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT pk_deleted_label PRIMARY KEY (mailbox_id, label_id_hash),
        CONSTRAINT fk_deleted_label_mailbox FOREIGN KEY (mailbox_id) REFERENCES categories.mailbox (id),
        CONSTRAINT ck_deleted_label_hash CHECK (label_id_hash ~ '^[0-9a-f]{64}$')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories.label_confirmation (
        mailbox_id varchar(64) NOT NULL,
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        plan_hash char(64) NOT NULL,
        skipped_ids text[] NOT NULL DEFAULT '{}',
        channel varchar(16) NOT NULL DEFAULT 'operator',
        actor_digest char(64) NOT NULL DEFAULT repeat('0', 64),
        at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT pk_label_confirmation PRIMARY KEY (mailbox_id, id),
        CONSTRAINT uq_label_confirmation_mailbox UNIQUE (mailbox_id),
        CONSTRAINT fk_label_confirmation_mailbox FOREIGN KEY (mailbox_id) REFERENCES categories.mailbox (id),
        CONSTRAINT ck_label_confirmation_channel CHECK (channel IN ('telegram', 'web', 'operator'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories.label_restore_request (
        mailbox_id varchar(64) NOT NULL,
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        channel varchar(16) NOT NULL DEFAULT 'operator',
        actor_digest char(64) NOT NULL DEFAULT repeat('0', 64),
        at timestamptz NOT NULL DEFAULT now(),
        processed_at timestamptz,
        CONSTRAINT pk_label_restore_request PRIMARY KEY (mailbox_id, id),
        CONSTRAINT fk_label_restore_request_mailbox FOREIGN KEY (mailbox_id) REFERENCES categories.mailbox (id),
        CONSTRAINT ck_label_restore_request_channel CHECK (channel IN ('telegram', 'web', 'operator'))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_label_restore_request_open ON categories.label_restore_request (mailbox_id)"
    " WHERE processed_at IS NULL",
)
_TABLE_NAMES = (
    "managed_label",
    "label_migration",
    "label_rename_item",
    "label_empty_since",
    "deleted_label",
    "label_confirmation",
    "label_restore_request",
)

# The data. Both statements only add what is missing, so a rerun after a crash completes and never duplicates.
_COPY = (
    "INSERT INTO categories.managed_label (mailbox_id, label_id, role, category_id, label_name) "
    "SELECT mailbox_id, label_id, 'category', category_id, label_name FROM categories.category_label "
    "ON CONFLICT DO NOTHING",
    "INSERT INTO categories.label_migration (mailbox_id, state) "
    "SELECT m.id, CASE WHEN EXISTS (SELECT 1 FROM categories.category_label c "
    "WHERE c.mailbox_id = m.id AND c.label_name LIKE 'Assistant/%') "
    "OR EXISTS (SELECT 1 FROM categories.gmail_label g WHERE g.mailbox_id = m.id AND g.name LIKE 'Assistant/%') "
    "THEN 'pending' ELSE 'done' END FROM categories.mailbox m ON CONFLICT DO NOTHING",
)

_SETTINGS = (
    "ALTER TABLE settings.schedule ADD COLUMN IF NOT EXISTS label_wait_minutes smallint NOT NULL DEFAULT 720 "
    "CONSTRAINT ck_schedule_label_wait CHECK (label_wait_minutes BETWEEN 5 AND 720)",
    "ALTER TABLE settings.schedule ADD COLUMN IF NOT EXISTS label_protection_days smallint NOT NULL DEFAULT 7 "
    "CONSTRAINT ck_schedule_label_protection CHECK (label_protection_days BETWEEN 1 AND 30)",
    "ALTER TABLE settings.schedule ADD COLUMN IF NOT EXISTS label_retention_days smallint NOT NULL DEFAULT 30 "
    "CONSTRAINT ck_schedule_label_retention CHECK (label_retention_days BETWEEN 7 AND 90)",
    "ALTER TABLE categories.list_settings ADD COLUMN IF NOT EXISTS other_label text NOT NULL DEFAULT 'Other' "
    "CONSTRAINT ck_list_settings_other_label CHECK (char_length(other_label) BETWEEN 1 AND 225)",
    "ALTER TABLE categories.list_settings ALTER COLUMN archive_label SET DEFAULT 'Archive'",
)

_ACTOR = "encode(sha256(convert_to(session_user::text, 'UTF8')), 'hex')"
_REQUEST_DERIVE = f"""
CREATE OR REPLACE FUNCTION categories.label_request_derive() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    NEW.at := now();
    NEW.channel := CASE session_user
                     WHEN 'mail_triage_runtime' THEN 'telegram'
                     WHEN 'web_settings_runtime' THEN 'web'
                     ELSE 'operator'
                   END;
    NEW.actor_digest := {_ACTOR};
    RETURN NEW;
END
$$
"""

# Only the confirmation function (current_user is the definer inside it) moves a plan to ``confirmed``; a plan that is
# empty of work may go straight to ``done``. ``done`` is final and the hash is fixed once the plan is confirmed.
_GUARD = """
CREATE OR REPLACE FUNCTION categories.label_migration_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state = 'confirmed' THEN
            RAISE EXCEPTION 'a plan is confirmed through the confirmation only' USING ERRCODE = 'MC409';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.mailbox_id <> OLD.mailbox_id
       OR (NEW.plan_hash IS DISTINCT FROM OLD.plan_hash AND OLD.state <> 'pending') THEN
        RAISE EXCEPTION 'the plan is fixed' USING ERRCODE = 'MC409';
    END IF;
    IF NEW.state <> OLD.state THEN
        IF OLD.state = 'pending' AND NEW.state = 'confirmed' AND current_user = 'categories_definer' THEN
            NULL;
        ELSIF OLD.state = 'confirmed' AND NEW.state = 'done' THEN
            NULL;
        ELSIF OLD.state = 'pending' AND NEW.state = 'done' AND NOT EXISTS (
                  SELECT 1 FROM categories.label_rename_item i
                   WHERE i.mailbox_id = OLD.mailbox_id AND i.state = 'planned') THEN
            NULL;
        ELSE
            RAISE EXCEPTION 'this state change is not allowed' USING ERRCODE = 'MC409';
        END IF;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END
$$
"""

_PLAN_HASH = """
CREATE OR REPLACE FUNCTION categories.label_plan_hash(p_mailbox text) RETURNS text
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT encode(sha256(convert_to(coalesce(jsonb_agg(
               jsonb_build_array(i.label_id, i.old_name, i.new_name) ORDER BY i.label_id COLLATE "C"
           ), '[]'::jsonb)::text, 'UTF8')), 'hex')
      FROM categories.label_rename_item i WHERE i.mailbox_id = p_mailbox
$$
"""

_CONFIRM = """
CREATE OR REPLACE FUNCTION categories.confirm_label_rename(p_mailbox text, p_plan_hash text, p_skipped text[])
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_state text;
    v_stored text;
    v_skipped text[];
    v_id uuid;
    v_hash text;
    v_known text[];
BEGIN
    SELECT m.state, m.plan_hash INTO v_state, v_stored
      FROM categories.label_migration m WHERE m.mailbox_id = p_mailbox FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'there is no rename plan' USING ERRCODE = 'MC409';
    END IF;
    v_skipped := coalesce(ARRAY(SELECT DISTINCT s FROM unnest(coalesce(p_skipped, '{}'::text[])) s ORDER BY s), '{}');
    SELECT c.id, c.plan_hash, c.skipped_ids INTO v_id, v_hash, v_known
      FROM categories.label_confirmation c WHERE c.mailbox_id = p_mailbox;
    IF FOUND THEN
        IF v_hash = p_plan_hash AND v_known = v_skipped THEN
            RETURN v_id;
        END IF;
        RAISE EXCEPTION 'the plan was confirmed with other values' USING ERRCODE = 'MC409';
    END IF;
    IF v_state <> 'pending' OR v_stored IS NULL OR p_plan_hash IS DISTINCT FROM v_stored
       OR v_stored <> categories.label_plan_hash(p_mailbox) THEN
        RAISE EXCEPTION 'the plan does not match what was confirmed' USING ERRCODE = 'MC409';
    END IF;
    IF EXISTS (SELECT 1 FROM unnest(v_skipped) s WHERE NOT EXISTS (
                   SELECT 1 FROM categories.label_rename_item i WHERE i.mailbox_id = p_mailbox AND i.label_id = s)) THEN
        RAISE EXCEPTION 'a skipped label is not in the plan' USING ERRCODE = 'MC409';
    END IF;
    INSERT INTO categories.label_confirmation (mailbox_id, plan_hash, skipped_ids)
    VALUES (p_mailbox, p_plan_hash, v_skipped) RETURNING id INTO v_id;
    UPDATE categories.label_migration SET state = 'confirmed' WHERE mailbox_id = p_mailbox;
    RETURN v_id;
END
$$
"""

_RESTORE = """
CREATE OR REPLACE FUNCTION categories.request_label_restore(p_mailbox text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    v_state text;
    v_id uuid;
BEGIN
    SELECT m.state INTO v_state FROM categories.label_migration m WHERE m.mailbox_id = p_mailbox FOR UPDATE;
    IF NOT FOUND OR v_state NOT IN ('confirmed', 'done') THEN
        RAISE EXCEPTION 'no label was renamed' USING ERRCODE = 'MC409';
    END IF;
    SELECT r.id INTO v_id FROM categories.label_restore_request r
     WHERE r.mailbox_id = p_mailbox AND r.processed_at IS NULL;
    IF FOUND THEN
        RETURN v_id;
    END IF;
    INSERT INTO categories.label_restore_request (mailbox_id) VALUES (p_mailbox) RETURNING id INTO v_id;
    RETURN v_id;
END
$$
"""

_FUNCTIONS = (
    "categories.label_request_derive()",
    "categories.label_migration_guard()",
    "categories.label_plan_hash(text)",
    "categories.confirm_label_rename(text, text, text[])",
    "categories.request_label_restore(text)",
)
_TRIGGERS = (
    ("label_migration_guard", "BEFORE INSERT OR UPDATE ON categories.label_migration", "label_migration_guard"),
    ("label_confirmation_derive", "BEFORE INSERT ON categories.label_confirmation", "label_request_derive"),
    ("label_restore_derive", "BEFORE INSERT ON categories.label_restore_request", "label_request_derive"),
)
# What the definer functions need, nothing else (the owner role keeps its rights through grants.sql as well).
_DEFINER_RIGHTS = (
    "GRANT SELECT, UPDATE ON categories.label_migration TO categories_definer",
    "GRANT SELECT ON categories.label_rename_item TO categories_definer",
    "GRANT SELECT, INSERT ON categories.label_confirmation, categories.label_restore_request TO categories_definer",
    "GRANT UPDATE (processed_at) ON categories.label_restore_request TO categories_definer",
)


def upgrade() -> None:
    """Create the tables, copy the data, add the settings, then the guard, the functions and the rights."""
    for statement in (*_TABLES, *_COPY, *_SETTINGS):
        op.execute(statement)
    for function_sql in (_REQUEST_DERIVE, _GUARD, _PLAN_HASH, _CONFIRM, _RESTORE):
        op.execute(function_sql)
    for name, when, function in _TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {when.rsplit(' ON ', 1)[1]}")
        op.execute(f"CREATE TRIGGER {name} {when} FOR EACH ROW EXECUTE FUNCTION categories.{function}()")
    for function in _FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
        op.execute(f"ALTER FUNCTION {function} OWNER TO categories_definer")
    for statement in _DEFINER_RIGHTS:
        op.execute(statement)


def downgrade() -> None:
    """Remove every object of this revision; the data of revision 0029 is not touched."""
    for function in reversed(_FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {function} CASCADE")
    for table in reversed(_TABLE_NAMES):
        op.execute(f"DROP TABLE IF EXISTS categories.{table}")
    op.execute("ALTER TABLE categories.list_settings ALTER COLUMN archive_label DROP DEFAULT")
    op.execute("ALTER TABLE categories.list_settings DROP COLUMN IF EXISTS other_label")
    for column in ("label_retention_days", "label_protection_days", "label_wait_minutes"):
        op.execute(f"ALTER TABLE settings.schedule DROP COLUMN IF EXISTS {column}")
