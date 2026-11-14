---
intent: INT-002
feature: web-settings
---

# U-web-settings-06: Migration 0008: web_auth, web guard line, contract version, notice record (R1)

- Layer: backend (database; agent migration chain)
- Contract: migration `0008` in `agents/mail-triage/migrations`: schema `web_auth` with `login_request` (id, username key, code hash, `expires_at`, attempts, `created_at` (the request time, which starts the cooldown), `sent_at` (empty when the send failed; only sent codes count towards the hourly cap), `dead_at`; rows are marked dead when replaced or used and kept for one hour so the hourly cap can be counted), `session` (hashed id, hashed username, `last_seen_at`, `absolute_expires_at`), `security_event` (kind from a CHECK-constrained set, result, hashed username or null, request id, client key, window; no free text) and `web_lock` (single row); the web line in the guard of 0006 (`session_user = 'web_settings_runtime'` gives channel `web`, `updated_by` must match `^web:[0-9a-f]{32}$`, `version = old + 1`); the cursor for web notices in `poll_state`; the notice token record table; `settings.contract_version()`; every new function revoked from `PUBLIC`. Grants are not here (U-07).
- Files: `agents/mail-triage/migrations/versions/0008_web_auth.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/tests/db/test_web_auth_migration.py`, `agents/mail-triage/tests/db/test_settings_migration.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given revision 0007 with settings data, When migrated to 0008, Then the `web_auth` tables, the cursor column and the notice table exist, data is unchanged and models match the schema (no drift) (type: happy; level: db).
  2. Given 0008, When downgraded, Then schema, tables, column, function and the web guard line are gone, the 0006 guard works as before, and upgrading again is clean (type: edge; level: db).
  3. Given a write by session user `web_settings_runtime` (created in the test), When it updates the row with a valid `updated_by`, Then `updated_via` is `web` and the audit record has `db_role` web (AC-9, W-10) (type: happy; level: db).
  4. Given a write by the web role with `updated_by` of `telegram:1`, `web:` plus 31 hex, upper-case hex or empty, When executed, Then SQLSTATE 42501 for each (AC-17, W-10) (type: security; level: db).
  5. Given the web role with a version of old plus 2, and one claiming `updated_via = 'telegram'`, When executed, Then 42501 (AC-17) (type: security; level: db).
  6. Given the 0006 guard tests for the agent role and the owner, When run, Then they pass unchanged (type: happy; level: db).
  7. Given `settings.contract_version()`, When called, Then it returns the schema's integer constant, and no function added by 0008 has `PUBLIC` execute (W-8) (type: security; level: db).
  8. Given `security_event`, `login_request` and `session`, When their columns are inspected, Then kinds are a CHECK set, hashes are fixed-length, attempts is bounded 0 to 5 and there is no unbounded text column (W-13, W-15) (type: security; level: db).
  9. Given `web_lock`, When a second row is inserted, Then it is refused (ADR-0033) (type: edge; level: db).
  10. Given the notice token record, When two records with the same token are inserted, Then the second is refused (ADR-0033) (type: edge; level: db).
