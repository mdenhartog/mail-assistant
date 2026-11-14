---
intent: INT-002
feature: web-settings
---

# U-web-settings-13: Security event store (R1; the alert is R2)

- Layer: backend
- Contract: `SecurityEvents.record(kind, request_id, client, username_hash=None)` writes `web_auth.security_event`; kinds `code_refused` (wrong, expired, used, exhausted, no cookie; the R2 alert counts these), `code_request_refused` (cooldown, hourly cap), `mail_failed`, `session_start`, `session_end`, `csrf_refused`, `rate_limited`, `lock_refused`; one row per kind, client and window (`floor(clock.now() / 60)`); an unknown username is stored only as its digest (U-10); one structured log line per recorded event with kind, result, client class and request id. Changed by U-54: a repeat of `code_refused` increments `count`; U-63 adds `code_invalid`.
- Files: `backend/app/security_events.py`, `backend/tests/test_security_events.py`
- Depends on: U-web-settings-07, U-web-settings-09, U-web-settings-10
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-fastapi
- Criteria:
  1. Given a `code_refused` event for the canary username, When recorded, Then the row has kind, result, request id, client and the digest of the username, and the canary appears nowhere in the table or the log (AC-20, W-13, W-15) (type: security; level: db).
  2. Given ten identical events from one client in one window, When recorded, Then one row exists; after the `FakeClock` crosses the window boundary (59.9 s then 60.0 s) a second row is added (AC-20) (type: edge; level: db).
  3. Given two different kinds from one client in one window, When recorded, Then both are kept (type: edge; level: db).
  4. Given a recorded event, When the log is captured, Then one line has kind, result and request id and no code, cookie, username or address (AC-20, W-15) (type: security; level: db).
  5. Given an unknown kind string, When recorded, Then it is refused before the database (type: error; level: unit).
  6. Given the insert fails, When an event is recorded inside a refusal, Then the caller still returns its refusal and the log has the error class only (type: error; level: db).
  7. Given a `mail_failed` event, When recorded, Then it carries no address and no error text (AC-29, W-16) (type: security; level: db).
