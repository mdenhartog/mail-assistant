---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-11: Api: the plan view with part and pause reason, and the 409

- Component: api
- Layer: backend
- Contract: The plan view (read only) adds `part`, `series_checked`, `series_estimate` and `pause_reason` (`Literal` of the fixed set or null). It never carries the cursor, a message id, a sender, a subject or error text. `POST /api/resort-requests` answers 409 with a plain message while a series is unfinished and stores nothing. OpenAPI is exported and `docs/api` is regenerated.
- Files: `backend/app/resort_repo.py`, `backend/app/routers/resort_requests.py`, `backend/app/services/resort_requests.py`, `backend/app/models/`, `backend/openapi.json`, `docs/api/README.md`, tests under `backend/tests/`
- Depends on: U-daily-budget-partial-plan-03
- Parallel: yes
- Guardrails: guardrail-python, guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a signed-in session, When the plan of a paused part is read, Then the body holds the part, the totals and one fixed pause reason and no cursor, message id, sender, subject or error text (SAC-16, AC 23). (type: security)
  2. Given no session, When the plan is read, Then 401 (SAC-16). (type: security)
  3. Given a series with part 1 applied and part 2 not started, When a new request is sent, Then 409 and nothing is stored (SAC-11, AC 17). (type: security)
  4. Given a new request with no unfinished series, When it is sent, Then it is stored as before (AC 12). (type: happy)
  5. Given the api role, When it reads the plan, Then it uses the column-level grant and `build_cursor` is never selected (SAC-16). (type: security)
  6. Given the contract, When `export_openapi --check` runs, Then the file matches the code. (type: happy)
  7. Given a request that was stored and no plan yet, When the same user sends a second request, Then it is refused with 409 and one row exists (double submit). (type: edge)
  8. Given the refusal is decided in the database function of U-03, When the api gets its typed error, Then it maps it to 409 with a plain message and holds no second definition of "unfinished". (type: edge)
