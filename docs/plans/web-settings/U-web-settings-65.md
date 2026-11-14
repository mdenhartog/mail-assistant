---
intent: INT-002
feature: web-settings
---

# U-web-settings-65: Contract version, count integrity, column grants, event index (R1; challenge round 2; SEC2-02, SEC2-03, RT2-06, RT2-09)

- Layer: database (migration 0012), backend, agent
- Contract: migration 0012 raises `settings.contract_version()` and the backend `EXPECTED_CONTRACT_VERSION` (down lowers it), so `/readyz` is 503 on a database older or newer than the api; a `BEFORE UPDATE` trigger on `web_auth.security_event` allows only `NEW.count = OLD.count + 1` with every other column unchanged, plus `CHECK (count >= 1)`; the agent role gets `SELECT (id, kind, at, count)` only; an index on `(kind, at)`.
- Files: `agents/mail-triage/migrations/versions/0012_event_integrity.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/db/models.py`, `backend/app/db.py`, `agents/mail-triage/tests/db/test_event_integrity_migration.py`, `backend/tests/db/test_readiness_contract.py`
- Depends on: U-web-settings-54, U-web-settings-48
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-fastapi, guardrail-pytest
- Criteria:
  1. Given the chain at 0009, 0010 or 0011, When `/readyz` runs, Then 503; at 0012, Then 200 (type: security; level: db).
  2. Given the web role, When it sets `count` to 0, to old+2 or changes any other column, Then it is refused; `count + 1` works (W-8, W-13) (type: security; level: db).
  3. Given the agent role, When it selects `username_hash`, `client_key` or `request_id` from `security_event`, Then 42501; `id`, `kind`, `at` and `count` work (type: security; level: db).
  4. Given the alert query on a large table, When explained, Then it uses the `(kind, at)` index (type: edge; level: db).
  5. Given migration 0012, When run up, down and up, Then it is reversible (type: edge; level: db).
