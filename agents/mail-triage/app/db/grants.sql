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
GRANT INSERT (mailbox_id, message_id, list_version, topic_id, extra_id, source, source_ref)
    ON categories.filing TO mail_triage_runtime;
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
-- The review page shows the threshold and the delay the approval uses; it only reads them (the agent writes them).
GRANT SELECT ON categories.apply_config TO web_settings_runtime;
GRANT SELECT (mailbox_id, plan_id, id, sender_name, sender_address, subject, old_category_id, new_category_id,
    decision, state, reason) ON categories.plan_item TO web_settings_runtime;
GRANT SELECT ON categories.move_back_request TO web_settings_runtime;
GRANT INSERT (mailbox_id, plan_id) ON categories.move_back_request TO web_settings_runtime;

-- The agent writes the columns of a plan it builds, applies and announces, nothing else: a plan is born ``building`` and
-- only approve_plan (the definer) schedules it and sets apply_after (RED-006; the triggers are the second line).
REVOKE INSERT, UPDATE ON categories.plan FROM mail_triage_runtime;
GRANT SELECT ON categories.plan TO mail_triage_runtime;
GRANT INSERT (mailbox_id, list_version, cap) ON categories.plan TO mail_triage_runtime;
GRANT UPDATE (state, build_cursor, checked_count, unclear_count, estimate_total, not_looked_at, last_activity_at,
    apply_run_id, apply_lease_until, announced_at) ON categories.plan TO mail_triage_runtime;
GRANT SELECT ON categories.plan_item, categories.plan_decision, categories.plan_approval, categories.apply_audit,
    categories.move_back_request TO mail_triage_runtime;
GRANT INSERT (mailbox_id, plan_id, message_id, sender_name, sender_address, subject, old_category_id, new_category_id)
    ON categories.plan_item TO mail_triage_runtime;
GRANT UPDATE (state, reason, attempts) ON categories.plan_item TO mail_triage_runtime;
GRANT INSERT (mailbox_id, plan_id, message_id, old_label, new_label, channel, kind) ON categories.apply_audit
    TO mail_triage_runtime;
GRANT UPDATE (processed, run_id, lease_until) ON categories.move_back_request TO mail_triage_runtime;
-- The Move back button of Telegram asks as the agent: the trigger refuses a plan that is not applied and writes the
-- actor (the agent login) and the time itself.
GRANT INSERT (mailbox_id, plan_id) ON categories.move_back_request TO mail_triage_runtime;
-- The non-login role that owns the definer functions keeps the rights they run with, for tables added later too.
GRANT USAGE, CREATE ON SCHEMA categories TO categories_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA categories TO categories_definer;
-- The decision functions are the api's alone (the agent decides nothing for the user).
GRANT EXECUTE ON FUNCTION categories.record_decision(text, uuid, integer, jsonb, text) TO web_settings_runtime;
GRANT EXECUTE ON FUNCTION categories.approve_plan(text, uuid, integer) TO web_settings_runtime;
-- The agent replaces a plan and drops the items it moved through these two functions: it has no DELETE right on plan_item.
GRANT EXECUTE ON FUNCTION categories.replace_plan(text, uuid) TO mail_triage_runtime;
GRANT EXECUTE ON FUNCTION categories.remove_applied_items(text, uuid) TO mail_triage_runtime;

-- The daily re-file report (U-mail-categories-25): no runtime role has any right on categories.refile_report. The agent
-- appends a row through this function alone (it runs as the definer) and never reads one back; retention is the purge.
GRANT EXECUTE ON FUNCTION categories.record_refile_report(text, integer, integer, integer, integer, integer)
    TO mail_triage_runtime;

-- Category contract v2 (INT-008, U-label-structure-05, ADR-0053, ADR-0058). Senders and list settings follow the
-- insert-only version rules of category: select and insert for both roles, nothing else (the deferred trigger accepts a
-- row only for a version created in the same transaction). The upload preview is the api's alone: it creates a
-- preview and marks it used; the agent has no right on it. Expired previews go with purge_expired().
GRANT SELECT, INSERT ON categories.category_sender, categories.list_settings TO web_settings_runtime, mail_triage_runtime;
GRANT SELECT ON categories.upload_preview TO web_settings_runtime;
GRANT INSERT (mailbox_id, id, session_digest, file_hash, base_version, content, expires_at)
    ON categories.upload_preview TO web_settings_runtime;
GRANT UPDATE (used_at) ON categories.upload_preview TO web_settings_runtime;

-- Skipped sender rules (INT-008, U-label-structure-36): the agent counts them in the transaction of the filing; the api
-- only reads them. Rows without a skip for 90 days go with purge_expired().
GRANT SELECT ON categories.sender_skip TO web_settings_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON categories.sender_skip TO mail_triage_runtime;

-- Sort again (INT-008, U-label-structure-20, ADR-0056). The api asks through request_resort alone (it has no INSERT on
-- the request table) and reads the requests, the plan kind and the new item columns. The agent reads the requests, names
-- the kind and the request of a plan it builds (the threshold is copied by a trigger, never chosen) and writes the pair,
-- the confidence and the tip of an item. Only approve_system_plan (the agent's alone) approves a system plan and sets the
-- decision source; the api has no right on it (SQLSTATE 42501).
GRANT SELECT ON categories.resort_request TO web_settings_runtime, mail_triage_runtime;
GRANT SELECT (old_topic_id, old_extra_id, new_topic_id, new_extra_id, confidence_pct, decision_source, tip)
    ON categories.plan_item TO web_settings_runtime;
GRANT INSERT (kind, request_id) ON categories.plan TO mail_triage_runtime;
GRANT INSERT (old_topic_id, old_extra_id, new_topic_id, new_extra_id, confidence_pct)
    ON categories.plan_item TO mail_triage_runtime;
GRANT UPDATE (tip) ON categories.plan_item TO mail_triage_runtime;
GRANT EXECUTE ON FUNCTION categories.request_resort(text, numeric) TO web_settings_runtime;
GRANT EXECUTE ON FUNCTION categories.approve_system_plan(uuid) TO mail_triage_runtime;

-- The label boundary (INT-010, U-label-prefix-removal-02, ADR-0060, ADR-0061). The agent writes its own tables: the
-- managed labels, the plan, the timers and the record of deleted labels. It starts and finishes the state of the rename
-- plan, but only confirm_label_rename moves it to confirmed (a trigger refuses the agent). The api reads the state, the
-- plan items and the deleted labels and writes nothing here except through the two functions: it has no right on
-- managed_label, label_empty_since, the confirmation or the restore table.
GRANT SELECT, INSERT, UPDATE, DELETE ON categories.managed_label, categories.label_rename_item,
    categories.label_empty_since, categories.deleted_label TO mail_triage_runtime;
GRANT SELECT ON categories.label_migration, categories.label_confirmation, categories.label_restore_request
    TO mail_triage_runtime;
GRANT INSERT (mailbox_id, state, plan_hash), UPDATE (state, plan_hash) ON categories.label_migration
    TO mail_triage_runtime;
GRANT UPDATE (processed_at) ON categories.label_restore_request TO mail_triage_runtime;
GRANT SELECT ON categories.label_migration, categories.label_rename_item, categories.deleted_label
    TO web_settings_runtime;
GRANT EXECUTE ON FUNCTION categories.label_plan_hash(text) TO mail_triage_runtime;
GRANT EXECUTE ON FUNCTION categories.confirm_label_rename(text, text, text[]) TO web_settings_runtime;
GRANT EXECUTE ON FUNCTION categories.request_label_restore(text) TO web_settings_runtime;
-- The Settings page saves the label cleanup values with the rest of the schedule; the CHECK constraints hold the bounds.
GRANT UPDATE (label_wait_minutes, label_protection_days, label_retention_days) ON settings.schedule
    TO web_settings_runtime;
