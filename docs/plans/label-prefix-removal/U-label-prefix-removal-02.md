---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-02: Migration 0030 (expand): managed labels, rename plan, migration state, timers, settings and the deleted-label record

- Component: mail-triage agent
- Layer: backend
- Contract: Alembic migration 0030 with downgrade: `categories.managed_label(mailbox_id, role category|other|archive, category_id null, label_id, label_name)` filled from `category_label`; `label_migration(mailbox_id, state pending|confirmed|done)`; `label_rename_item`; `label_empty_since(label_id, empty_since, last_seen_empty)`; `deleted_label(label_id_hash, name, deleted_at)`; settings columns for the waiting time, protection and retention; `list_settings.other_label`. Grants: the agent role writes its tables; the api role reads only what the spec shows and gets `SECURITY DEFINER` functions for the confirmation and the restore. It inserts no list version.
- Files: `agents/mail-triage/migrations/versions/0030_label_boundary.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/app/db/grants.sql`, tests under `agents/mail-triage/tests/db/`
- Depends on: U-label-prefix-removal-01
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest, guardrail-python
- Criteria:
  1. Given a database at 0029 with `category_label` rows, When 0030 runs, Then `managed_label` holds one row per row and no list version is added. (type: happy)
  2. Given 0030 has run, When it runs again, Then nothing changes (AC 16). (type: edge)
  3. Given a crash after part of the data was copied, When 0030 runs again, Then the data is complete and unduplicated (AC 16). (type: edge)
  4. Given 0030, When downgraded, Then the new objects are gone and the 0029 data is intact. (type: happy)
  5. Given the api role, When it inserts into `managed_label`, `label_empty_since` or `deleted_label`, Then it is refused; it can read the plan items and call only the confirmation and restore functions. (type: security)
  6. Given the confirmation function and a plan hash that does not match, When called, Then it refuses and writes nothing. (type: security)
  7. Given a settings value outside its bounds, When written by any role, Then the CHECK constraint refuses it (AC 33). (type: error)
  8. Given an existing mailbox with `Assistant/` labels, When 0030 has run, Then `label_migration` is `pending`; with no such label it is `done`. (type: edge)
