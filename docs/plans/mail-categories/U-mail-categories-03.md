---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-03: Categories schema, roles and list-side functions

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: Alembic revision in the agent chain: schema `categories` list half (`mailbox`, `category_identity`, `list_version`, `category` insert-only with deferred version trigger, `list_audit` via SECURITY DEFINER deferred trigger, `category_count`, `gmail_label`, `category_label`, `filing`, `list_cursor`, `rejection`, `telegram_action`, `apply_config`), the api and agent grants of the design matrix for those tables, `purge_expired()` without parameters, readiness revision (at least).
- Files: agents/mail-triage/migrations/versions/*, agents/mail-triage/app/db/grants.sql, agents/mail-triage/app/db/models.py, agents/mail-triage/tests/db/test_categories_*.py
- Depends on: U-mail-categories-01, U-mail-categories-02
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the migration, When run up and down on a database with data, Then the schema appears and goes away and other schemas are untouched (MC-18) (type: happy)
  2. Given the matrix table x column x operation x role, When each statement runs as the api or agent role, Then everything outside the design matrix fails with SQLSTATE 42501 (AC-20) (type: security)
  3. Given a new list version, When the api inserts version = expected + 1 with its rows in one transaction, Then it is stored and `list_audit` has one record with channel and actor digest derived by the database (AC-2, AC-36) (type: happy)
  4. Given a race of two inserts for the same version, Then one wins and the other gets a unique violation (409, AC-3) (type: edge)
  5. Given an insert of a version not created in the same transaction or with a gap, Then the deferred trigger refuses it (type: security)
  6. Given the agent role, When it calls `purge_expired()` with rows younger than their retention (also with a changed session clock), Then they survive; a direct DELETE on an audit table fails (AC-56) (type: security)
  7. Given owner fixtures that backdate rows, When `purge_expired()` runs, Then only rows past retention are removed (type: happy)
  8. Given a seeded token table in another schema, When the api role selects it, Then PostgreSQL refuses (AC-20) (type: security)
  9. Given two mailbox ids, When the repository reads, Then it never returns the other's rows (AC-37) (type: security)
