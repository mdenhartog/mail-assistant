-- The single source of the runtime role's rights (ADR-0025, ADR-0026). Run by the migration job as the owner role,
-- after the migrations, and by the tests. The runtime role owns nothing and cannot run DDL. Idempotent.
--
-- Whenever a migration adds a table, add its grant here; nothing is granted by default.

REVOKE ALL ON SCHEMA public FROM mail_triage_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM mail_triage_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mail_triage_runtime;
REVOKE ALL ON SCHEMA settings FROM mail_triage_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA settings FROM mail_triage_runtime;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA settings FROM mail_triage_runtime;

-- Mail, alerts and dialogue state: per table, exactly what the code does (ADR-0030 item 1). No DDL (no CREATE on the
-- schema, no ownership), no TRUNCATE, and a delete only where the code deletes.
GRANT USAGE ON SCHEMA public TO mail_triage_runtime;
-- The mail trail is append-only: the runtime role can add audit records and the overview log, never change or remove them.
GRANT SELECT, INSERT ON audit_log, overview_log TO mail_triage_runtime;
-- Created and updated, never deleted (state moves forward; the token, poll and catch-up rows are upserted).
GRANT SELECT, INSERT, UPDATE ON
    mail_item, alert, draft, oauth_token, poll_state, catchup_state
    TO mail_triage_runtime;
-- The one pending dialogue is replaced and removed.
GRANT SELECT, INSERT, UPDATE, DELETE ON conversation TO mail_triage_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mail_triage_runtime;

-- The start-up readiness check reads the Alembic revision (ADR-0025); the runtime role can never change it.
GRANT SELECT ON alembic_version TO mail_triage_runtime;

-- Settings: read, create and replace the single schedule row. No delete and no truncate. settings_change may only be
-- read (Undo needs the previous values, U-quiet-hours-05): the audit trigger writes it as the owner (SECURITY
-- DEFINER), so the runtime role can only add records through a schedule change and can never insert, update, delete
-- or truncate them directly.
GRANT USAGE ON SCHEMA settings TO mail_triage_runtime;
GRANT SELECT, INSERT, UPDATE ON settings.schedule TO mail_triage_runtime;
GRANT SELECT ON settings.settings_change TO mail_triage_runtime;
