---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-04: List API

- Component: api
- Layer: backend
- Release: R1
- Contract: GET `/api/categories` and PUT `/api/categories` as in the design; 200, 409 (version, `not-ready`), 422 `problems`, 429 above the account limit; CSRF, Origin, web lock; OpenAPI regenerated; readiness check on the revision.
- Files: backend/app/categories_*.py, backend/app/main.py (route registration), docs/api/openapi.json, backend/tests/test_categories_*.py
- Depends on: U-mail-categories-02, U-mail-categories-03
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-fastapi, guardrail-pydantic, guardrail-openapi
- Criteria:
  1. Given a signed-in user, When GET, Then the list with counts, 'Other', older categories and `ready` is returned (AC-1) (type: happy)
  2. Given a valid list and the current version, When PUT, Then 200, a new version and audit; an unchanged list makes no version (AC-2) (type: happy)
  3. Given each invalid name or description rule, When PUT, Then 422 with `problems` and nothing stored; 'Other' cannot be renamed or deleted (AC-2, AC-4, AC-8) (type: error)
  4. Given a stale version or the seed not yet written, When PUT, Then 409 with the current list or `not-ready` (AC-3, AC-49) (type: edge)
  5. Given 11 saves in an hour for the account (limit 10), Then the 11th gets 429, also from a new session (AC-33) (type: security)
  6. Given no session, a missing CSRF token, a wrong Origin or the web lock, Then 401 or 403 with the generic body (AC-22, AC-32) (type: security)
  7. Given a markup or script in a name, Then it is stored and returned as text; responses carry `Cache-Control: no-store` (AC-21) (type: security)
  8. Given the OpenAPI document, When schemathesis runs with a session and CSRF, Then no 5xx and the schema matches (type: happy)
