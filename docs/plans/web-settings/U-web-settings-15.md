---
intent: INT-002
feature: web-settings
---

# U-web-settings-15: Session store, cookie and lock check (R1)

- Layer: backend
- Contract: `SessionStore.create(username_hash, now) -> (cookie_value, Session)` (new random id each time through `IdSource`; only the hash of the id is stored), `get(cookie_value, now)`, `touch`, `delete`; `session_cookie(value)` builds `__Host-session` (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, Max-Age 43200); `require_session` (marker `session`) uses the pure rules of U-11; while `web_auth.web_lock` is set every lookup answers 401 and deletes the sessions.
- Files: `backend/app/auth/session.py`, `backend/app/core/security.py`, `backend/tests/auth/test_session.py`
- Depends on: U-web-settings-05, U-web-settings-09, U-web-settings-11, U-web-settings-13
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a created session, When the cookie is built, Then name `__Host-session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, Max-Age 43200, a 256-bit value (AC-7, W-3) (type: security; level: unit).
  2. Given a session last seen at 14:00:00 (`FakeClock`), When used at 14:29:59 and 14:30:00, Then accepted, then 401 (AC-7) (type: edge; level: db).
  3. Given activity every 20 minutes from 08:00:00, When used at 19:59:59 and 20:00:00, Then accepted, then 401 (AC-7) (type: edge; level: db).
  4. Given two sign-ins, When both create sessions, Then the ids differ, and a cookie presented before sign-in is never adopted (AC-7, W-3) (type: security; level: db).
  5. Given the table read as the owner, When inspected, Then only the hash of the id and the username digest are stored (W-3) (type: security; level: db).
  6. Given no cookie, an unknown cookie or an expired session, When a protected route is called, Then 401 with the generic body (AC-2) (type: error; level: api).
  7. Given `web_lock` set, When a valid session calls a protected route, Then 401, the sessions are deleted and a `lock_refused` event is recorded once per window (AC-27, ADR-0033) (type: security; level: db).
  8. Given each authorised request, When served, Then `last_seen_at` moves to the clock's now (type: happy; level: db).
  9. Given the logout path, When a session is deleted, Then a `session_end` event is recorded (AC-20) (type: happy; level: db).
