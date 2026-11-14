---
intent: INT-002
feature: web-settings
---

# U-web-settings-22: Settings write route PUT (R1)

- Layer: backend
- Contract: `PUT /api/settings` (session, CSRF, Origin, `LimitGuard("api")`) takes `{values, version}`: format check, `schedule_policy.validate`, `repository.write`; 200 `Settings`, 409 `Conflict409` with the current `Settings`, 422 `problems: [{field, rule, value, example}]` mapped by U-20, 415 for a non-JSON body.
- Files: `backend/app/routers/settings.py`, `backend/tests/test_settings_write.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-19, U-web-settings-21
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given a valid `PUT` at the current version, When sent with session and token, Then 200 with the new `Settings` and the next version (AC-9) (type: happy; level: api).
  2. Given an overview inside the quiet hours, When `PUT`, Then 422 with `field: overviewAt`, the same rule text and example as Telegram, nothing stored (AC-10) (type: error; level: api).
  3. Given malformed times (`7pm`, `24:00`, `07:00:30`, a number), an unknown zone, `../etc` and an over-long zone, When `PUT`, Then 422 and nothing stored (AC-10) (type: security; level: api).
  4. Given an old version, When `PUT`, Then 409 with the current `Settings` and nothing stored (AC-11) (type: edge; level: api).
  5. Given an extra property in the body or a non-JSON content type, When `PUT`, Then 422 or 415 and nothing stored (AC-15) (type: security; level: api).
  6. Given a zone `<script>alert(1)</script>`, When `PUT`, Then 422 and the body carries it only as a JSON string (AC-14) (type: security; level: api).
  7. Given no session, a session without the token, a wrong `Origin` and a locked web, When `PUT`, Then 401 or 403 and nothing is written (AC-2, AC-8, AC-27) (type: security; level: api).
  8. Given a body over 8192 bytes, When the real guard is in place (U-24) or a stub guard refuses, Then the request never reaches validation (AC-16) (type: edge; level: api).
  9. Given a write whose audit trigger fails, When `PUT`, Then a generic 500 and nothing stored (AC-17) (type: security; level: db).
  10. Given the OpenAPI, When regenerated, Then `PUT /api/settings` is listed with the session and csrf markers (AC-15; U-45 lists `POST /api/settings/reset` too) (type: security; level: ci).
