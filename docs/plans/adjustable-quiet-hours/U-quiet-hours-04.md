---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-04: Migration 0004: settings schema, trigger, constraints

- Layer: backend (database)
- Contract: schema `settings` with `schedule` (single row, version, CHECKs) and `settings_change` (append-only, filled by a trigger); table `conversation` (single row); column `alert.release_at`. Run under the owner role; the runtime role gets minimal grants from one SQL source (ADR-0025, ADR-0026). Upgrades and downgrades cleanly.
- Files: `migrations/versions/0004_settings.py`, `app/db/models.py`, `app/db/grants.sql` (the one source of the role grants, also used by U-15a), `tests/db/test_settings_migration.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given revision 0003 with alerts, When migrated, Then the tables exist, alerts keep their data and `release_at` is null (type: happy).
  2. Given the migration, When downgraded, Then the schema, tables and column are gone and other data is unchanged (type: edge).
  3. Given a parametrised table with one row per CHECK name (minutes out of range, start equal to end, window outside 60-720 minutes, overview or remind inside the window, bad zone pattern, second row), When inserted directly, Then PostgreSQL refuses each (AC-34) (type: security).
  4. Given a row insert or update, When it succeeds, Then `settings_change` has a record with via, by, old and new, written by the trigger (AC-30) (type: happy).
  5. Given a runtime role created in the test from `grants.sql`, When it updates, deletes or truncates `settings_change`, runs DDL, or changes `session_replication_role`, Then PostgreSQL refuses (SQLSTATE 42501) (AC-30) (type: security).
  6. Given a fresh database, When all migrations run, Then the models match the schema (no drift) (type: happy).
  7. Given `settings_change`, When its columns are inspected, Then via and by are length-limited and there is no free-text column (type: security).
