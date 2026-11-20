---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-17: Plan, approve and move-back API

- Component: api
- Layer: backend
- Release: R2
- Contract: GET `/api/plan`, GET `/api/plan/items`, POST `/api/plan/decisions`, POST `/api/plan/approve`, POST `/api/plan/{id}/move-back`; they call the database functions; 403 only for lock, CSRF and Origin, 409 for plan, count and state mismatches; no sender filter in the URL; OpenAPI regenerated.
- Files: backend/app/plan_*.py, docs/api/openapi.json, backend/tests/test_plan_*.py
- Depends on: U-mail-categories-12
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-fastapi, guardrail-openapi
- Criteria:
  1. Given a plan, When GET, Then state, progress, groups, counts, `applyAfter` and the last plan are returned (AC-12, AC-43) (type: happy)
  2. Given items, When GET with a page, Then at most 100 items with sender name and address and subject as text and `no-store` (AC-12, AC-30) (type: security)
  3. Given a decision with the right plan id and count, Then it is recorded; with a stale plan id or count, Then 409 and nothing is approved (AC-32) (type: error)
  4. Given more than 200 ids, Then it is refused (AC-34) (type: security)
  5. Given approve, Then the state and `applyAfter` are returned; a repeat returns the same (type: edge)
  6. Given move-back for an applied plan, Then one request is stored; for another plan, Then 409 (type: happy)
  7. Given no session, no CSRF, a wrong Origin or the lock, Then the generic 401 or 403 (AC-22, AC-32) (type: security)
  8. Given the OpenAPI document, When schemathesis runs, Then no 5xx (type: happy)
