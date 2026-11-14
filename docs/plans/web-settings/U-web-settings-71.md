---
intent: INT-002
feature: web-settings
---

# U-web-settings-71: The web role cannot forge security events; expired notice tokens are purged (R1; challenge round 3; RT3-05, SEC3-04)

- Layer: database (migration 0013), agent
- Contract: migration 0013 grants the web role `INSERT` on `web_auth.security_event` only for `(kind, result, username_hash, request_id, client_key, "window")`, makes `id` `GENERATED ALWAYS`, and adds a `BEFORE INSERT` trigger that sets `at = now()`, `count = 1` and `window = floor(extract(epoch from now()) / 60)`; the retention purge also deletes `web_notice_token` rows whose `expires_at` has passed.
- Files: `agents/mail-triage/migrations/versions/0013_event_insert_guard.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/app/db/purge.py`, `agents/mail-triage/tests/db/test_event_insert_guard.py`, `agents/mail-triage/tests/db/test_purge.py`
- Depends on: U-web-settings-65, U-web-settings-49
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the web role, When it inserts a `security_event` with an explicit `id`, `at` or `count`, Then it is refused (42501); a normal insert works and gets the server's `at`, `count` 1 and window (W-8, W-13) (type: security; level: db).
  2. Given an expired and a live notice token, When the purge runs, Then only the expired one is gone (W-11) (type: happy; level: db).
  3. Given migration 0013, When run up, down and up, Then it is reversible (type: edge; level: db).
