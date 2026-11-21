---
intent: INT-008
feature: label-structure
---

# U-label-structure-19: Api: the archive label setting (R2)

- Component: api
- Layer: backend
- Contract: `archiveLabel` on `GET` and `PUT /api/categories` (list-level field in `list_settings`), validated by `category-policy` (`validate_archive_label`, ADR-0059); a change is one list version with the audit record and the Telegram change notice; included in the upload and export.
- Files: `backend/app/schemas/categories.py`, `backend/app/services/categories.py`, `docs/api/openapi.json`, tests
- Depends on: U-label-structure-11, U-label-structure-18
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-pytest
- Criteria:
  1. Given a valid archive name, When saved, Then it is stored in the new version and the notice is sent. (type: happy)
  2. Given a Gmail system label name (any case), a name equal to or below a category label, a name inside `Assistant/` other than `Assistant/Archive`, or a category below the archive label, When saved or uploaded, Then the field shows the reason and nothing is stored. (type: error)
  3. Given an upload or export, When used, Then the archive label is part of the file. (type: happy)
  4. Given the old environment setting, When the api starts, Then it is not read. (type: edge)
