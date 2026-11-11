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

-- Web sign-in and settings (INT-002, ADR-0033). The agent role gets the web lock (it sets it from "Undo and lock" and
-- lifts it again), the notice token record and, through poll_state above, the notice cursor. It gets nothing else in
-- web_auth: the sessions, login requests and security events belong to the web role alone.
REVOKE ALL ON SCHEMA web_auth FROM mail_triage_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA web_auth FROM mail_triage_runtime;
GRANT USAGE ON SCHEMA web_auth TO mail_triage_runtime;
GRANT SELECT, INSERT, UPDATE ON web_auth.web_lock TO mail_triage_runtime;
-- A token is created with a notice, read when "Undo" is tapped, and removed once used or expired.
GRANT SELECT, INSERT, UPDATE, DELETE ON web_notice_token TO mail_triage_runtime;

-- The web role (ADR-0033): per table and per column, nothing on public and nothing on settings.settings_change. The
-- role is created by the migrate job; where it does not exist yet (before U-web-settings-08) this block is skipped.
DO $web$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_settings_runtime') THEN
        REVOKE ALL ON SCHEMA public FROM web_settings_runtime;
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM web_settings_runtime;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM web_settings_runtime;
        REVOKE ALL ON SCHEMA settings FROM web_settings_runtime;
        REVOKE ALL ON ALL TABLES IN SCHEMA settings FROM web_settings_runtime;
        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA settings FROM web_settings_runtime;
        REVOKE ALL ON SCHEMA web_auth FROM web_settings_runtime;
        REVOKE ALL ON ALL TABLES IN SCHEMA web_auth FROM web_settings_runtime;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA web_auth FROM web_settings_runtime;

        -- The schedule: read it, create the first row and replace its values; no delete, no truncate. The version,
        -- the channel and the actor are checked by the guard; updated_at is the server's.
        GRANT USAGE ON SCHEMA settings TO web_settings_runtime;
        GRANT SELECT ON settings.schedule TO web_settings_runtime;
        GRANT INSERT (id, zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by)
            ON settings.schedule TO web_settings_runtime;
        GRANT UPDATE (zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by)
            ON settings.schedule TO web_settings_runtime;
        GRANT EXECUTE ON FUNCTION settings.contract_version() TO web_settings_runtime;

        -- Sign-in state. Security events are append-only; the lock is read here and written by the agent only.
        GRANT USAGE ON SCHEMA web_auth TO web_settings_runtime;
        GRANT SELECT, INSERT, UPDATE, DELETE ON web_auth.login_request, web_auth.session TO web_settings_runtime;
        GRANT SELECT, INSERT ON web_auth.security_event TO web_settings_runtime;
        GRANT SELECT ON web_auth.web_lock TO web_settings_runtime;
        GRANT USAGE, SELECT ON SEQUENCE web_auth.security_event_id_seq TO web_settings_runtime;
    END IF;
END
$web$;
