---
intent: INT-002
feature: web-settings
---

# U-web-settings-07: Grants for the web role and the agent's new rights (R1)

- Layer: backend (database)
- Contract: `grants.sql` (still the one source) gains `web_settings_runtime`: `SELECT` on `settings.schedule`; `INSERT` and `UPDATE` limited to the columns `(id,) zone, quiet_start, quiet_end, overview_at, remind_at, version, updated_via, updated_by`; execute on `settings.contract_version()`; on `web_auth`: `login_request` insert/select/update/delete, `session` insert/select/update/delete, `security_event` insert/select, `web_lock` select; nothing on `public`, nothing on `settings_change`. The agent role gains `INSERT, UPDATE, SELECT` on `web_auth.web_lock`, the rights it needs on the notice token table and the cursor (`poll_state` is already granted) and nothing else in `web_auth`.
- Files: `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/tests/db/test_web_role_grants.py`, `agents/mail-triage/tests/db/test_settings_grants.py`
- Depends on: U-web-settings-06
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the web role, When it selects and updates the allowed columns and inserts the first row of `settings.schedule`, Then each works (type: happy; level: db).
  2. Given the web role, When it updates any column outside the list, or deletes or truncates `settings.schedule`, Then 42501 (AC-17) (type: security; level: db).
  3. Given `mail_item`, `alert`, `draft`, `oauth_token`, `audit_log`, `poll_state`, `catchup_state`, `overview_log`, `conversation` and `alembic_version`, When the web role selects from each, Then 42501 (AC-17, W-8) (type: security; level: db).
  4. Given `settings.settings_change`, When the web role selects, inserts, updates, deletes or truncates, Then 42501 (AC-17) (type: security; level: db).
  5. Given the web role, When it runs `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` or `SET session_replication_role`, Then 42501 (AC-17) (type: security; level: db).
  6. Given `web_auth`, When the web role updates `web_lock`, updates `security_event`, or deletes `security_event`, Then 42501 (type: security; level: db).
  7. Given the agent role, When it inserts and updates `web_auth.web_lock`, Then it works; when it reads or writes `session`, `login_request` or `security_event`, Then 42501 (ADR-0033) (type: security; level: db).
  8. Given the real agent role `mail_triage_runtime`, When it inserts and updates the notice token record and the cursor, Then it works; the web role on both gets 42501 (ADR-0033) (type: security; level: db).
  9. Given `grants.sql` run twice, When compared, Then the same grants result; the 0006 grant tests for the agent role pass unchanged (type: edge; level: db).
