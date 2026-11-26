---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-19: Api follows the policy v3 rules: list save, upload and the contract cases

- Component: api
- Layer: backend
- Contract: Found while building unit 16: `backend/app/categories_write.py` calls `validate_list` and `validate_archive_label` with the old arguments, and `backend/tests/test_categories_api.py` and `test_category_upload_service.py` use the removed rule `name_label_exists`, the `labels` and `adoptable` inputs and the old archive helpers. The api passes the current "Other" and archive names as `settings`, adopts an existing label instead of refusing it, reports the new rule `name_setting_clash` and runs the shared `category_cases.json`.
- Files: `backend/app/categories_write.py`, `backend/app/categories_repo.py`, `backend/app/services/category_upload.py`, tests under `backend/tests/`
- Depends on: U-label-prefix-removal-16, U-label-prefix-removal-02
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a list category whose name equals an existing Gmail label, When the list is saved or previewed, Then it is accepted and shown as adopted, with no refusal (AC 19). (type: happy)
  2. Given a category equal to the current name of the "Other" or the archive setting, When saved, Then 422 with `name_setting_clash` (AC 13). (type: error)
  3. Given reserved names (`Archive`, `Other`, `archive/Taxes`) and Gmail system labels, When saved or uploaded, Then they are refused in any case. (type: security)
  4. Given the shared `category_cases.json`, When the api suite runs it, Then every row passes. (type: happy)
  5. Given the default archive label of a new installation, When read, Then it is `Archive` (AC 12). (type: happy)
  6. Given the source, When searched, Then `validate_archive_label`, `LABEL_PREFIX` and `name_label_exists` appear nowhere in the backend. (type: edge)
  7. Given the upload preview, When it counts categories, Then adopted labels are counted, not refused. (type: edge)
