---
intent: INT-002
feature: web-settings
---

# U-web-settings-17: Request-code endpoint (R1)

- Layer: backend
- Contract: `POST /auth/request-code` (public, Origin check, `LimitGuard("signin")`) with `{username}`: limits first (client bucket, then the per-username cooldown and hourly cap), then the same `200 {maskedAddress, expiresAt, resendAfterSeconds}` and the same `Set-Cookie: __Host-login` (random id, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, Max-Age 600) for the configured and an unknown username; for the configured one a login request is created, the code from `CodeSource` is handed to the mailer; for an unknown one a dummy hash and the same code path timing are used and nothing is sent. A failed send gives the same 200, is logged and recorded as `mail_failed`, and still counts for the cooldown and the cap (ADR-0036). 429 with `Retry-After` for the cooldown and the hourly cap.
- Files: `backend/app/routers/auth.py`, `backend/app/auth/request_code.py`, `backend/tests/auth/test_request_code.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-12, U-web-settings-13, U-web-settings-16
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-oauth2-oidc, guardrail-pydantic
- Criteria:
  1. Given the configured username, When a code is requested, Then 200 with the masked address, `expiresAt` 10 minutes ahead, `resendAfterSeconds` 60, the cookie, and exactly one message in the fake mailer with the code of `FakeCodes` (AC-29) (type: happy; level: api).
  2. Given the configured and an unknown username, When requested, Then status, body shape and values (except per-request fields), header names, cookie attributes and cookie length are identical, and the mailer got no message for the unknown one (AC-30, W-2) (type: security; level: api).
  3. Given both cases, When the work done is counted (calls to hash and store, with the fake clock advancing a fixed step per call), Then the same number of steps run, so the timing class is the same (AC-30, W-2) (type: security; level: api).
  4. Given the mailer fails, When a code is requested, Then the answer equals the success answer, a `mail_failed` event exists, the failed send starts the cooldown (a second request within 60 s gets 429) and does not count towards the hourly cap, and nothing about the cause or the address is in the response or log (AC-29, AC-31, W-15) (type: security; level: api).
  5. Given a second request at 59 s and at 60 s after the first, whether the first send succeeded or failed, When requested, Then 429 with `Retry-After: 1`, then 200 and the earlier code no longer works (AC-5, AC-31) (type: edge; level: api).
  6. Given five sent codes in an hour (spaced 60 s) and a sixth request, When requested, Then the sixth gets 429 with `Retry-After` until the oldest sent code falls out of the hour (59 min 59 s still 429, 60 min 1 s 200) and no message is sent; Given instead five failed sends spaced 60 s, Then the sixth request is answered 200 and its message is sent, because the cap counts only sent codes (AC-5, AC-31, W-7) (type: edge; level: api). Superseded by D-16 and U-53: a failed send counts.
  7. Given a wrong or missing `Origin`, When requested, Then 403 and no login request row (AC-8, W-4) (type: security; level: api).
  8. Given a username of 65 characters, a control character or a non-string, When requested, Then 422 before any work and no log line contains it (W-15) (type: security; level: api).
  9. Given a refused request (429), When it happens, Then a `code_request_refused` event is recorded once per window (AC-20, AC-31) (type: security; level: db).
  10. Given the request-code route, When the inventory is read, Then it is `public` and carries the `signin` guard (AC-15, AC-16) (type: security; level: unit).
