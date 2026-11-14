---
intent: INT-002
feature: web-settings
---

# U-web-settings-21: Settings write repository (R1)

- Layer: backend (database)
- Contract: `SettingsRepository.write(values, expected_version, username_hash) -> StoredSettings` as about 40 lines of SQLAlchemy Core: one `UPDATE ... WHERE version = :v RETURNING`, or `INSERT ... ON CONFLICT DO NOTHING` at version 0; `VersionConflict` carries the current row; the guard sets the channel and the audit trigger records the change in the same transaction. This unit extends `settings_repo.py` written by U-20.
- Files: `backend/app/settings_repo.py`, `backend/tests/db/test_settings_repo.py`, `backend/tests/db/test_contract_fixture.py`
- Depends on: U-web-settings-07, U-web-settings-09, U-web-settings-20
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pydantic
- Criteria:
  1. Given no row, When written at version 0, Then version 1 and the row exists; a second writer at version 0 gets `VersionConflict` (AC-9, AC-11) (type: happy; level: db).
  2. Given a write at version 1, When committed, Then version 2, exactly one `settings_change` record with `db_role` of the web role, channel `web` and `updated_by` of the form `web:<32 hex>` (AC-9, W-10) (type: happy; level: db).
  3. Given two sessions that read the same version and an explicit barrier, When both write, Then exactly one succeeds, the other gets `VersionConflict` with the current row, one audit record exists (AC-11, W-12) (type: edge; level: db).
  4. Given a stale version, When written, Then `VersionConflict` and nothing changes (AC-11) (type: error; level: db).
  5. Given the audit trigger function is replaced in the test by one that raises, When a write runs, Then the whole write is rolled back and the caller gets an error, not a success (AC-17) (type: security; level: db).
  6. Given a write that sets `version` to old plus 2, When executed through the role, Then 42501 (AC-17) (type: security; level: db).
  7. Given `contract/settings_cases.json`, When run through the repository, Then outcomes match the package and the agent (AC-26) (type: happy; level: db).
  8. Given a zone value `'; drop table settings.schedule; --`, When written, Then the statement is parameterised, the database CHECK refuses it and nothing changes (AC-10) (type: security; level: db).
  9. Given a failure path with the canary zone, When logs are captured, Then no record contains the canary (type: security; level: db).
