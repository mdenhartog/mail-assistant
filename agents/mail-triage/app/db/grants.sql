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
-- lifts it again), the notice token record and, through poll_state above, the notice cursor. It may also read the
-- security events, to warn about wrong codes (U-web-settings-48, ADR-0039). It gets nothing else in web_auth: the
-- sessions and login requests belong to the web role alone, and it never writes an event.
REVOKE ALL ON SCHEMA web_auth FROM mail_triage_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA web_auth FROM mail_triage_runtime;
GRANT USAGE ON SCHEMA web_auth TO mail_triage_runtime;
-- A row means locked; only a Telegram command lifts the lock, by deleting the row (no truncate).
GRANT SELECT, INSERT, UPDATE, DELETE ON web_auth.web_lock TO mail_triage_runtime;
-- The wrong-code alert adds up the counts of the code_refused events; read only (no insert, update or delete), and
-- only the four columns it uses: the username digest, the client key and the request id stay with the web role
-- (SEC2-03).
GRANT SELECT (id, kind, at, count) ON web_auth.security_event TO mail_triage_runtime;
-- A token is created with a notice, read when "Undo" is tapped, and removed once used or expired.
GRANT SELECT, INSERT, UPDATE, DELETE ON web_notice_token TO mail_triage_runtime;

-- The web role (ADR-0033): per table and per column, nothing on public and nothing on settings.settings_change. The
-- migrate job creates the role before this file runs; a missing role makes the script fail, on purpose.
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
GRANT SELECT, INSERT, UPDATE, DELETE ON web_auth.session TO web_settings_runtime;
-- A login request keeps who asked (username_key, client_hash) and its code hash from the insert on; only the counters
-- and the times of its life change.
GRANT SELECT, INSERT, DELETE ON web_auth.login_request TO web_settings_runtime;
GRANT UPDATE (attempts, sent_at, dead_at) ON web_auth.login_request TO web_settings_runtime;
-- An event is inserted by the web role through six columns only: the id is GENERATED ALWAYS, and the trigger of 0013
-- gives the row the server's time, a count of 1 and a window within one of the server's minute (RT3-05, SEC3-04).
GRANT SELECT ON web_auth.security_event TO web_settings_runtime;
GRANT INSERT (kind, result, username_hash, request_id, client_key, "window") ON web_auth.security_event
    TO web_settings_runtime;
-- A repeat of a counted kind raises the count; nothing else of an event ever changes.
GRANT UPDATE (count) ON web_auth.security_event TO web_settings_runtime;
GRANT SELECT ON web_auth.web_lock TO web_settings_runtime;
-- No grant on web_auth.security_event_id_seq: an identity column needs none, and the web role cannot advance it.
