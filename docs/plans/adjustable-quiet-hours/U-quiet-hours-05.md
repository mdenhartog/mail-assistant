---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-05: Settings store

- Layer: integration (testcontainers PostgreSQL, `tests/db/conftest.py`) and contract
- Contract: `SettingsStore.read() -> StoredSettings | None` (policy, version, updated info); `write(policy, expected_version, via, by) -> StoredSettings` (whole row, validated, version check, `VersionConflict`); `undo(expected_version)`. Row-to-policy uses the shared validation.
- Files: `app/db/pg_settings_store.py`, `app/db/repos.py`, `tests/db/test_settings_store.py`, `packages/schedule-policy/contract/settings_cases.json` (shared with `web-settings`)
- Depends on: U-quiet-hours-01, U-quiet-hours-04
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given no row, When read, Then `None`; When written with version 0, Then version 1 (type: happy).
  2. Given two sessions that read the same version and an explicit barrier (no sleeps), When both write, Then exactly one succeeds, the other gets `VersionConflict`, exactly one audit record exists and the row passes validation (AC-29) (type: edge).
  3. Given an invalid policy, When written, Then refused before the database and nothing changes (type: error).
  4. Given a write, When it commits, Then exactly one audit record exists (AC-30) (type: happy).
  5. Given an undo with the current version, Then the previous values return; with an old version, Then `VersionConflict` (AC-21) (type: edge).
  6. Given the shared fixture file of valid and invalid cases, When run through the store, Then the outcomes match the package (AC-36) (type: happy).
  7. Given a failure between validation and commit, When it happens, Then nothing is stored (AC-13) (type: error).
  8. Given a write to `Pacific/Kiritimati` and a failure path, When logs are captured, Then no record contains the zone or a token (AC-33) (type: security).
