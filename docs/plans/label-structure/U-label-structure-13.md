---
intent: INT-008
feature: label-structure
---

# U-label-structure-13: Api: export and template (R1)

- Component: api
- Layer: backend
- Contract: `GET /api/categories/export` (the current list as `mail-categories.yaml`, `schema: 1`) and `GET /api/categories/template` (template and example files); both session-protected GETs sent as attachments with `nosniff` and `no-store`.
- Files: `backend/app/routers/category_export.py`, `backend/app/services/category_export.py`, `docs/api/openapi.json`, tests
- Depends on: U-label-structure-04, U-label-structure-11
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pytest
- Criteria:
  1. Given the current list, When exported and uploaded unchanged, Then the preview shows no change and a confirm makes no new version. (type: happy)
  2. Given the export response, Then it has `Content-Disposition: attachment`, `nosniff` and `no-store` and the name `mail-categories.yaml`. (type: security)
  3. Given no session, Then the export and the template are refused. (type: security)
  4. Given the template and the example, When fetched, Then they parse without error. (type: happy)
  5. Given an export, Then it contains only the upload fields (no ids, no other mailbox). (type: security)
