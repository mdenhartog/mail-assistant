---
intent: INT-008
feature: label-structure
---

# U-label-structure-37: Api: the per-entry skipped counts (R1)

- Component: api
- Layer: backend
- Contract: `GET /api/categories` adds `skippedCount` (integer, at least 0) to every sender entry, read from `categories.sender_skip` (unit 36) for the entries of the current list only; an entry with no row has 0. The count is read-only: `PUT /api/categories` does not accept it (extra fields stay forbidden) and an upload ignores it. The OpenAPI document, the API reference and the web types (`pnpm --filter web gen:api`) are regenerated in this unit.
- Files: `backend/app/categories_repo.py`, `backend/app/services/categories.py`, `backend/app/schemas/categories.py`, `docs/api/openapi.json`, `docs/api/reference.md`, `apps/web/src/api/schema.d.ts`, tests in `backend/tests/`
- Depends on: U-label-structure-11, U-label-structure-36
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given counts for two entries of the current list, When the list is fetched, Then each entry carries its count and an entry without a row carries 0. (type: happy)
  2. Given a count row for an entry that is no longer on the list, When the list is fetched, Then it does not appear. (type: edge)
  3. Given a `PUT` body that contains `skippedCount`, Then it is refused with a 422 and nothing is written. (type: security)
  4. Given another mailbox's counts, When the list is fetched, Then they never appear. (type: security)
