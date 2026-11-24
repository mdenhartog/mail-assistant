---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-11: Api: the rename preview, the confirmation, the restore and the recently deleted record

- Component: api
- Layer: backend
- Contract: Routes: `GET` the rename preview (items with old name, new name, count, action), `POST` the confirmation with the plan hash and the skipped ids through the `SECURITY DEFINER` function (idempotent), `POST` restore, `GET` recently deleted (name, deleted-at) for the retention period; the migration state is shown.
- Files: `backend/app/routers/label_rename.py`, `backend/app/schemas/label_rename.py`, `backend/app/services/label_rename.py`, `docs/api/openapi.json`, tests under `backend/tests/`
- Depends on: U-label-prefix-removal-02, U-label-prefix-removal-10
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a pending plan, When the preview is read, Then it lists every label with old name, new name, mail count and action, and a summary of labels and mails. (type: happy)
  2. Given the preview and no confirmation, When the agent runs, Then nothing was changed (AC 5). (type: security)
  3. Given the confirmation with the right hash, When posted, Then one row is written; posted twice, Then still one. (type: happy)
  4. Given a wrong or replayed hash after the plan changed, When posted, Then 409 and nothing is written. (type: security)
  5. Given skipped ids in the confirmation, When posted, Then they are stored as skipped. (type: edge)
  6. Given a completed rename, When Restore is posted, Then the restore is requested once (AC 27). (type: happy)
  7. Given the recently deleted route, When read, Then it holds names only for the retention period and is read-only (AC 29). (type: security)
  8. Given no session or no CSRF token on the writes, When called, Then they are refused. (type: security)
