---
intent: INT-002
feature: web-settings
---

# U-web-settings-18: Verify-code endpoint and sign-in (R1)

- Layer: backend
- Contract: `POST /auth/verify-code` (public, Origin check, `LimitGuard("signin")`) with `{code, returnTo?}` and the `__Host-login` cookie: loads the request, checks it (U-16), and on `Ok` checks the web lock, creates the session (U-15), sets `__Host-session`, clears `__Host-login` and answers 204 with the validated return path in the body or a `Location`-free JSON `{returnTo}`; every failure answers one generic 400 whose body carries `attemptsLeft` only when the cookie names a live request, and clears `__Host-login` when the request is dead. Every outcome writes a security event.
- Files: `backend/app/routers/auth.py`, `backend/app/auth/verify_code.py`, `backend/tests/auth/test_verify_code.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-13, U-web-settings-15, U-web-settings-16
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-oauth2-oidc, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a requested code, When the right code is posted with the cookie, Then 204, a new `__Host-session`, `__Host-login` cleared, a `session_start` event, and `returnTo` is `/settings` (AC-7) (type: happy; level: api).
  2. Given a wrong code, an expired code (10:00), a used code, a code after 5 wrong attempts, a code from another browser's cookie, an old code after a new one, an unknown username's cookie and no cookie, When posted, Then each gets the same 400 body shape, no session exists, one test each (AC-3, AC-5, W-1) (type: security; level: api).
  3. Given wrong codes with a live request, When refused, Then the body has `attemptsLeft` 4, 3, 2, 1 in turn; with no cookie or a dead request the field is absent; the fifth wrong code clears `__Host-login` and a sixth attempt with the right code gets the generic 400 (AC-3, AC-5) (type: edge; level: api).
  4. Given two concurrent verify requests with the same right code and the same cookie, When both run, Then exactly one 204 and one 400, and exactly one session row exists (AC-3, W-1) (type: security; level: db).
  5. Given `returnTo` values `https://evil.example`, `//x`, `javascript:1`, When posted with the right code, Then the answer says `/settings` (AC-6, W-2) (type: security; level: api).
  6. Given `web_lock` set, When the right code is posted, Then no session and a `lock_refused` event, and the response status, body and headers are identical to the generic 400 of a wrong code with the request id as the only difference, with no explanation of the lock (AC-27, W-1) (type: security; level: db).
  7. Given a wrong or missing `Origin`, When posted, Then 403 and no attempt is counted (AC-8) (type: security; level: api).
  8. Given a refused code, When events are read, Then one `code_refused` event per client and window, with no code and no cookie value, and the canary code `424242` is in no log (AC-20, W-15) (type: security; level: db).
  9. Given a malformed body (`code` of 7 digits, letters, empty, an object), When posted, Then the same generic 400 and the attempt is not counted for a format error but the response is not distinguishable (AC-3, AC-15) (type: security; level: api).
