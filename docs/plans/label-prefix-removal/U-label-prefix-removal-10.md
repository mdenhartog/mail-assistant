---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-10: Api: settings for the waiting time, protection, retention and the names of Other and archive

- Component: api
- Layer: backend
- Contract: The existing settings route (the one the Settings page saves, with its draft and conflict handling) accepts and returns `waitingMinutes`, `protectionDays` and `retentionDays`; the list-settings route accepts and returns `otherLabel` and `archiveLabel` (extra fields forbidden on both), validate with `category-policy`, are audited and carry the defaults and ranges in the response; the OpenAPI document and the generated client are regenerated.
- Files: `backend/app/routers/settings.py`, `backend/app/schemas/settings.py`, `backend/app/services/settings.py`, `docs/api/openapi.json`, tests under `backend/tests/`
- Depends on: U-label-prefix-removal-01, U-label-prefix-removal-02
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the defaults, When the settings are read, Then they show 12 hours, 7 days, 30 days, `Other` and `Archive` with their ranges (AC 12, 33). (type: happy)
  2. Given a value inside its range, When saved, Then it is stored and read back (AC 33). (type: happy)
  3. Given a value outside its range, When saved, Then 422 with a message tied to the field (AC 33). (type: error)
  4. Given a name that clashes with a list category or a system label, When saved, Then it is refused (AC 13). (type: error)
  5. Given a request without a session or without the CSRF token, When it saves, Then it is refused. (type: security)
  6. Given a request with an unknown field, When saved, Then it is refused. (type: security)
  7. Given a protection below 1 day, When saved, Then it is refused (AC 34). (type: error)
  8. Given a change of the waiting time, When saved, Then it is audited without label names. (type: security)
