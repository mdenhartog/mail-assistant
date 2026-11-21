---
intent: INT-008
feature: label-structure
---

# U-label-structure-05: Migration for contract v2 (R1)

- Component: mail-triage
- Layer: backend
- Contract: one Alembic revision in the agent's chain (ADR-0025): `category.kind` and `category.notify` with defaults; new insert-only `category_sender` and `list_settings` with the deferred version trigger; rebuilt `filing` (`topic_id`, `extra_id`, `source`, `source_ref`); a unique key so an alert is written once per mail; `upload_preview`; grants for the api and agent roles; `purge_expired()` also removes expired previews; the migrate job reads `ARCHIVE_LABEL` once into the migrated `list_settings` rows. A working downgrade.
- Files: `agents/mail-triage/migrations/versions/<new revision>.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/db/migrate.py`, tests in `agents/mail-triage/tests/db/`
- Depends on: U-label-structure-02
- Parallel: yes
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the INT-004 list, When the migration runs, Then every category becomes a topic with no senders and no tick, ids and labels are unchanged, and no list version and no audit record is added. (type: happy)
  2. Given the migration ran, When it runs again, Then nothing changes; When the downgrade runs, Then the old columns and `category_id` are restored. (type: edge)
  3. Given a custom `ARCHIVE_LABEL` in the migrate job's environment, When the migration runs, Then it is stored in the migrated `list_settings` rows; without it the default `Assistant/Archive` is stored. (type: edge)
  4. Given the api role, When it reads or writes the new tables, Then the grant matrix holds (select and insert on `category_sender`, `list_settings`, `upload_preview`; nothing else new), and everything else is refused with SQLSTATE 42501. (type: security)
  5. Given two alerts for the same mail id, When the second is inserted, Then the key refuses it. (type: edge)
  6. Given an expired `upload_preview`, When `purge_expired()` runs, Then it is deleted and nothing else is. (type: edge)
