---
intent: INT-002
feature: web-settings
---

# U-web-settings-45: Reset to defaults: backend (R2)

- Layer: backend
- Contract: `POST /api/settings/reset` (session, CSRF, Origin, `LimitGuard("api")`) with `{version}` writes `DEFAULT_POLICY` through the same repository and validation as `PUT`; 200 `Settings`, 409 on an old version. The allow-list and the route inventory gain the path in this unit only.
- Files: `backend/app/routers/settings.py`, `backend/tests/test_settings_reset_api.py`, `backend/tests/test_route_inventory.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-22
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given a changed row, When reset at the current version, Then the defaults including the time zone are stored through the repository and 200 with the new `Settings` (AC-25) (type: happy; level: db).
  2. Given the reset, When the audit is read, Then one record with channel web and `updated_by` of the form `web:<32 hex>` exists (AC-25, W-10) (type: security; level: db).
  3. Given an old version, When reset, Then 409 with the current `Settings` and nothing changes (AC-11) (type: edge; level: api).
  4. Given no token, a wrong `Origin` or no session, When reset, Then 403 or 401 and nothing changes (AC-8, AC-25) (type: security; level: api).
  5. Given a GET on the route, When sent, Then 405 (AC-8) (type: security; level: api).
  6. Given the reset, When the agent next runs, Then a web notice follows like any web change (AC-13) (type: happy; level: agent).
  7. Given the route inventory, When read, Then the path is on the allow-list with the session and csrf markers (AC-15) (type: security; level: unit).
