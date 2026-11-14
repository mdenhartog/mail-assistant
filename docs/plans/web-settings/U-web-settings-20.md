---
intent: INT-002
feature: web-settings
---

# U-web-settings-20: Settings read: models, GET, RULES, field map, checked-in OpenAPI (R1)

- Layer: backend
- Contract: the read part of the settings API so the web can start next to the auth units. `Settings` `{values: {timeZone, quietStart, quietEnd, overviewAt, remindAt}, version, updatedAt, updatedVia}` (`HH:MM`, `additionalProperties: false`; at version 0 `updatedAt` and `updatedVia` are null, D-8), the schemas the write part will use (`SettingsUpdate`, `Problem422`, `Conflict409`) declared in the OpenAPI, `GET /api/settings` (session, `LimitGuard("api")`), `SettingsRepository.read()`, `schedule_policy.RULES` and the rule-to-field map `app/settings_fields.py` (pure), and `docs/api/openapi.json` regenerated. The write route is not in this unit.
- Files: `packages/schedule-policy/schedule_policy/policy.py`, `packages/schedule-policy/schedule_policy/__init__.py`, `backend/app/settings_repo.py`, `backend/app/settings_fields.py`, `backend/app/routers/settings.py`, `backend/tests/test_settings_read.py`, `docs/api/openapi.json`
- Depends on: U-web-settings-05, U-web-settings-09, U-web-settings-15
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a stored row, When `GET /api/settings`, Then the four values as `HH:MM`, version, `updatedAt` and `updatedVia`, and no actor field (AC-1, AC-15) (type: happy; level: api).
  2. Given no row, When `GET`, Then the defaults with `version: 0`, `updatedAt` and `updatedVia` null (AC-1, D-8) (type: edge; level: api).
  3. Given `RULES` exported by the package and the field map, When compared, Then every rule has a field and nothing extra; adding a rule to the package without a mapping fails the test (AC-10) (type: edge; level: unit).
  4. Given the rules `quiet_window_*`, `overview_in_quiet_hours`, `remind_in_quiet_hours`, `zone_unknown`, When mapped, Then start and end, overview, remind and zone fields as in the design (AC-10) (type: happy; level: unit).
  5. Given no session, an expired session and a locked web, When `GET`, Then 401 and nothing is read (AC-2, AC-27) (type: security; level: api).
  6. Given the exported OpenAPI, When read, Then it contains `Settings`, `SettingsUpdate`, `Problem422`, `Conflict409`, `additionalProperties: false` on each, the path `/api/settings` only with GET, and the web client types can be generated from it (AC-15) (type: happy; level: ci).
  7. Given the 31st request of one client in a window on a lowered limit and a `LimitGuard` fake that refuses, When `GET`, Then 429 (the route declares the guard) (AC-16) (type: edge; level: api).
  8. Given the package fixture `contract/settings_cases.json`, When the package tests run, Then they pass unchanged (AC-26) (type: happy; level: unit).
