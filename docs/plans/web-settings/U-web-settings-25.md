---
intent: INT-002
feature: web-settings
---

# U-web-settings-25: Walking skeleton at API level (M1)

- Layer: backend
- Contract: one test module that runs the whole first path in process, with fakes and a real database: request a code (read from `FakeMailer`), verify it, `GET /api/session`, `GET /api/settings`, `PUT /api/settings` once, `POST /auth/logout`. It exists to keep a working end-to-end path while later units add to it.
- Files: `backend/tests/test_walking_skeleton.py`
- Depends on: U-web-settings-18, U-web-settings-19, U-web-settings-22
- Parallel: no
- Guardrails: guardrail-pytest, guardrail-fastapi
- Criteria:
  1. Given a fresh database and fakes, When the allowed username signs in with the code from the fake mailer, Then `GET /api/session` shows the masked address and a token (AC-7) (type: happy; level: api).
  2. Given the session, When `GET /api/settings` then `PUT /api/settings` with a valid change and the token, Then version 0 becomes 1 and an audit record with channel web exists (AC-1, AC-9) (type: happy; level: db).
  3. Given the same path with a wrong code once, When retried with the right code, Then sign-in succeeds with the same request (attempt 2 of 5) (AC-3) (type: edge; level: api).
  4. Given the saved row, When read through the agent store, Then the agent sees the new values (AC-9, AC-26) (type: happy; level: db).
  5. Given logout, When the old cookie is used, Then 401 (AC-7) (type: security; level: api).
  6. Given the whole path, When logs are captured, Then no canary code, username, cookie or zone appears (W-15) (type: security; level: api).
