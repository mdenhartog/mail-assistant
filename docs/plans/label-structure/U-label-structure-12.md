---
intent: INT-008
feature: label-structure
---

# U-label-structure-12: Api: upload, preview, confirm and restore (R1)

- Component: api
- Layer: backend
- Contract: `POST /api/categories/upload` (the file; returns the preview id and the counts added, changed and removed with the removed categories), `POST /api/categories/upload/{id}/confirm` (one list version, audit, change notice), `POST /api/categories/restore-previous`; parsing by `category-policy` (U-label-structure-04); the preview row is bound to session, file hash, base version and expires after 15 minutes; CSRF and `Origin` checks; the hourly limit of a list save.
- Files: `backend/app/routers/category_upload.py`, `backend/app/services/category_upload.py`, `backend/app/schemas/category_upload.py`, `docs/api/openapi.json`, tests
- Depends on: U-label-structure-04, U-label-structure-11
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a valid file, When uploaded, Then a preview leads with the counts and nothing is stored. (type: happy)
  2. Given a preview, When confirmed, Then the whole list is replaced as one version with an audit record and the notice; When cancelled, Then nothing changes. (type: happy)
  3. Given an invalid or hostile file, When uploaded, Then every problem is returned with line and field and nothing is stored. (type: security)
  4. Given a confirm from another session, with a changed file hash, an expired or used preview id, or after the list changed, Then 409 and nothing is stored; a double submit makes one version. (type: security)
  5. Given an upload or confirm without the CSRF token or with a foreign `Origin`, Then 403; above the hourly limit, Then 429. (type: security)
  6. Given names that equal existing categories (NFKC, case folding), When confirmed, Then they keep their id; a name missing from the file deletes its category by the INT-004 path. (type: edge)
  7. Given a confirmed upload, When "restore previous" is used, Then a new version equals the previous one. (type: happy)
  8. Given canary strings in the file, Then they are not found in the log, access log, Sentry stub, Telegram stub or audit rows. (type: security)
