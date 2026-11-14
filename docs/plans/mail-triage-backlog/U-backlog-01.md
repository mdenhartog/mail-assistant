---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-01: Catch-up state table and backlog flag

- Layer: backend (database)
- Contract: migration `0003` creates `catchup_state(id int pk, started_at timestamptz not null, finished_at timestamptz null)` and adds `mail_item.backlog boolean not null default false`; models `CatchupState` and `MailItem.backlog`. The migration upgrades and downgrades cleanly and keeps existing rows.
- Files: `migrations/versions/0003_catch_up.py`, `app/db/models.py`, `tests/db/test_migrate.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a database at revision 0002 with mail items, When the migration runs, Then `catchup_state` exists and every existing mail has `backlog = false` (type: happy).
  2. Given revision 0003, When the migration is downgraded, Then the table and the column are gone and the other data is unchanged (type: edge).
  3. Given a fresh database, When all migrations run, Then the model metadata matches the schema (no drift) (type: happy).
