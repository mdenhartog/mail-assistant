---
intent: INT-002
feature: web-settings
---

# U-web-settings-19: CSRF, Origin, /api/session and logout (R1)

- Layer: backend
- Contract: the CSRF token is `HMAC(csrf_key, session_id)` compared in constant time (`app/auth/csrf.py`); `GET /api/session` (session, `Sec-Fetch-Site` same-origin) returns `{maskedAddress, csrfToken, idleExpiresAt, absoluteExpiresAt, noticeIntervalMinutes}`; `require_csrf` (marker `csrf`) needs `X-CSRF-Token` and `Origin` equal to the public origin (missing `Origin` or `Sec-Fetch-Site: cross-site` is refused with the one 403 body); `POST /auth/logout` (session, CSRF, Origin) answers 204, deletes the session and clears the cookie; a GET on a write route answers 405; no CORS.
- Files: `backend/app/auth/csrf.py`, `backend/app/routers/session.py`, `backend/app/routers/auth.py`, `backend/app/core/security.py`, `backend/tests/auth/test_csrf.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-15
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-oauth2-oidc
- Criteria:
  1. Given a session id, When the token is derived, Then it equals the HMAC, differs for another session id, and the comparison calls `hmac.compare_digest` (W-4) (type: security; level: unit).
  2. Given a same-origin `GET /api/session`, When answered, Then masked address, token, both expiry times and `noticeIntervalMinutes` from settings, and no username or full address (AC-15, W-15) (type: happy; level: api).
  3. Given `Sec-Fetch-Site: cross-site` on `GET /api/session`, When answered, Then 403 and no token (AC-8, W-4) (type: security; level: api).
  4. Given a write without the token, with a wrong token, and with a token of another session, When sent, Then 403 with the same body and nothing changes (AC-8, W-4) (type: security; level: api).
  5. Given a valid token with a wrong, missing or `null` `Origin`, or `Sec-Fetch-Site: cross-site`, When sent, Then 403 (AC-8, W-4) (type: security; level: api).
  6. Given a GET on a write route, When sent, Then 405 (AC-8) (type: security; level: api).
  7. Given a valid logout, When sent, Then 204, the session row is gone, the cookie is cleared and the old cookie then gets 401; Given a logout without the token, Then 403 and the session stays valid (AC-7, AC-8) (type: happy; level: db).
  8. Given two tabs of one session, When both use the token, Then both work (type: edge; level: api).
  9. Given a preflight `OPTIONS` or any response, When inspected, Then there is no `Access-Control-Allow-*` header; a CSRF refusal records `csrf_refused` once per client and window (AC-8, AC-20, W-4) (type: security; level: db).
  10. Given the route inventory, When read, Then every `POST` and `PUT` operation except the two public sign-in routes has the `session` and `csrf` markers; one without fails (AC-15) (type: security; level: unit).
