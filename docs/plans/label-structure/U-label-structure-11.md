---
intent: INT-008
feature: label-structure
---

# U-label-structure-11: Api: the category list v2 (R1)

- Component: api
- Layer: backend
- Contract: `GET` and `PUT /api/categories` extended with `kind`, `notify`, `senders[]` (`entry`, `subdomains`), `generalInstructions`; the rules come from `category-policy` v2; versions stay insert-only with the audit record and the Telegram change notice; GET adds per-entry counts of skipped (not authenticated) mails; the OpenAPI schema and the contract test file are updated.
- Files: `backend/app/routers/categories.py`, `backend/app/services/categories.py`, `backend/app/schemas/categories.py`, `docs/api/openapi.json`, tests in `backend/tests/`
- Depends on: U-label-structure-02, U-label-structure-03, U-label-structure-05
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a valid list with nested names, kinds, senders, ticks and general instructions, When saved, Then it is stored as one new version with an audit record and the change notice. (type: happy)
  2. Given any rule violation of C-1 to C-6, When saved, Then 422 lists every problem with its field and nothing is stored. (type: error)
  3. Given a save without a change, Then no version and no notice. (type: edge)
  4. Given a stale version, Then 409. (type: error)
  5. Given the api role, When it writes outside its grants, Then SQLSTATE 42501 (matrix test); the response and logs carry no canary text from descriptions, senders or instructions. (type: security)
  6. Given the shared contract cases file, When the api tests run, Then every case passes and the OpenAPI schema matches its contract. (type: happy)
  7. Given a list with 100 categories of 100 senders, When read and saved, Then it works within a fixed time bound. (type: edge)
