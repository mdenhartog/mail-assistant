---
intent: INT-002
feature: web-settings
---

# U-web-settings-09: Database access, shared fixture and readiness (R1)

- Layer: backend
- Contract: async engine and session factory for the web role with `asyncpg` (`sqlalchemy[asyncio]`); the `ssl` argument is an `ssl.SSLContext` with `verify-full` behaviour (CA from the configured file, `check_hostname`, `CERT_REQUIRED`), the start-up check refuses any other mode in production; statement timeout from settings; `/readyz` compares `settings.contract_version()` with the expected constant instead of the agent's Alembic head; start-up removes expired `login_request` and `session` rows using `Clock`; the shared DB fixture (applies the agent chain as owner, `grants.sql`, connects as the web role, clean state per test) in `backend/tests/db/conftest.py`, which no later unit edits.
- Files: `backend/app/db.py`, `backend/app/routers/health.py`, `backend/app/startup.py`, `backend/pyproject.toml`, `backend/tests/db/conftest.py`
- Depends on: U-web-settings-04, U-web-settings-06, U-web-settings-07
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-fastapi
- Criteria:
  1. Given a migrated database, When `/readyz` is called, Then 200 (type: happy; level: db).
  2. Given a database whose `contract_version()` differs, When `/readyz` is called, Then 503 with a generic body (type: error; level: db).
  3. Given the database is down and the URL contains the canary password, When `/readyz` is called, Then 503 and the log has the error class and SQLSTATE only, no URL, no canary (type: security; level: db).
  4. Given the TLS settings, When the engine is built, Then the context has `check_hostname` true and `verify_mode` `CERT_REQUIRED`; production settings with `ssl` off, `require` or `verify-ca` are refused naming `database_url` (W-8, W-9) (type: security; level: unit).
  5. Given expired and valid rows in `login_request` and `session` and a `FakeClock`, When the app starts, Then only the expired rows are removed (type: edge; level: db).
  6. Given the source tree, When searched for `now()` and `CURRENT_TIMESTAMP` in SQL text, Then there is no hit (type: edge; level: unit).
  7. Given a statement slower than the timeout, When run, Then it is cancelled and the request ends 503 (W-7) (type: error; level: db).
  8. Given two tests in a row, When each uses the fixture, Then each starts from a clean schema state (type: edge; level: db).
