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

-- Mail categories (INT-004, ADR-0042, ADR-0047): per table and per column, exactly the matrix of the design. "api" is
-- the web role (web_settings_runtime), "agent" the runtime role. Nothing is granted by default; no DELETE on an audit
-- table for anyone; list_audit is written only by its SECURITY DEFINER trigger. The creation time, channel and actor of
-- a list version, and the time of a filing or a rejection, are the database's: no INSERT right on those columns.
REVOKE ALL ON SCHEMA categories FROM mail_triage_runtime, web_settings_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA categories FROM mail_triage_runtime, web_settings_runtime;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA categories FROM mail_triage_runtime, web_settings_runtime;
GRANT USAGE ON SCHEMA categories TO mail_triage_runtime, web_settings_runtime;

-- The api reads the list, the counts and the label names; it writes only list versions, their categories and the
-- identities of new categories. The agent may also seed version 1 and write Undo.
GRANT SELECT ON categories.mailbox, categories.category_identity, categories.list_version, categories.category,
    categories.category_count, categories.gmail_label TO web_settings_runtime;
GRANT INSERT (mailbox_id, id) ON categories.category_identity TO web_settings_runtime, mail_triage_runtime;
GRANT INSERT (mailbox_id, version) ON categories.list_version TO web_settings_runtime, mail_triage_runtime;
GRANT INSERT ON categories.category TO web_settings_runtime, mail_triage_runtime;
GRANT EXECUTE ON FUNCTION categories.contract_version() TO web_settings_runtime, mail_triage_runtime;

GRANT SELECT ON categories.mailbox, categories.category_identity, categories.list_version, categories.category,
    categories.list_audit, categories.filing, categories.rejection, categories.telegram_action,
    categories.apply_config TO mail_triage_runtime;
GRANT INSERT ON categories.mailbox TO mail_triage_runtime;
-- Replaced each cycle, or moved forward by the agent: the derived tables and the cursor.
GRANT SELECT, INSERT, UPDATE, DELETE ON categories.category_count, categories.gmail_label, categories.category_label,
    categories.list_cursor TO mail_triage_runtime;
-- Appended only (retention is the owner's purge_expired()).
GRANT INSERT (mailbox_id, message_id, list_version, category_id) ON categories.filing TO mail_triage_runtime;
GRANT INSERT (mailbox_id, message_id, list_version) ON categories.rejection TO mail_triage_runtime;
-- A button is created and consumed once: only used_at ever changes.
GRANT INSERT (mailbox_id, nonce_hash, chat_id, kind, target, expires_at) ON categories.telegram_action
    TO mail_triage_runtime;
GRANT UPDATE (used_at) ON categories.telegram_action TO mail_triage_runtime;
-- The apply threshold and delay come from the agent's deployment configuration; the api never touches them.
GRANT INSERT, UPDATE ON categories.apply_config TO mail_triage_runtime;
-- The agent triggers the retention purge; the function decides what goes, whatever the agent supplies.
GRANT EXECUTE ON FUNCTION categories.purge_expired() TO mail_triage_runtime;

-- Plan half (U-mail-categories-12, ADR-0046, ADR-0047). The api reads plans and the columns of an item the page shows
-- (not the message id), and asks for a move back; every decision and approval goes through the functions below.
-- The agent writes plans and items, moves an item through apply with state and reason only (never the decision), and
-- appends the apply audit. Nobody has DELETE: retention is purge_expired().
GRANT SELECT ON categories.plan TO web_settings_runtime;
GRANT SELECT (mailbox_id, plan_id, id, sender_name, sender_address, subject, old_category_id, new_category_id,
    decision, state, reason) ON categories.plan_item TO web_settings_runtime;
GRANT SELECT ON categories.move_back_request TO web_settings_runtime;
GRANT INSERT (mailbox_id, plan_id) ON categories.move_back_request TO web_settings_runtime;

GRANT SELECT, INSERT, UPDATE ON categories.plan TO mail_triage_runtime;
GRANT SELECT ON categories.plan_item, categories.plan_decision, categories.plan_approval, categories.apply_audit,
    categories.move_back_request TO mail_triage_runtime;
GRANT INSERT (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, old_category_id, new_category_id)
    ON categories.plan_item TO mail_triage_runtime;
GRANT UPDATE (state, reason) ON categories.plan_item TO mail_triage_runtime;
GRANT INSERT (mailbox_id, plan_id, message_id, old_label, new_label, channel) ON categories.apply_audit
    TO mail_triage_runtime;
GRANT UPDATE (processed) ON categories.move_back_request TO mail_triage_runtime;
-- The decision functions are the api's alone (the agent decides nothing for the user).
GRANT EXECUTE ON FUNCTION categories.record_decision(text, uuid, integer, jsonb, text) TO web_settings_runtime;
