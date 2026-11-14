---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-09: Persistence

- Layer: backend (adapter)
- Contract: SQLAlchemy models and Alembic migration for `mail_item`, `alert`, `draft`, `audit_log`, `oauth_token`, `poll_state`; repositories; `try_claim(message_id)`; single-replica lock.
- Files: `app/db/models.py`, `app/db/repos.py`, `migrations/versions/0001_initial.py`, `tests/db/*`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the migration, When upgraded and downgraded, Then both succeed and the schema matches the models (happy).
  2. Given the same Gmail message id twice, When `try_claim` runs, Then only the first succeeds (edge; AC-12).
  3. Given two processes, When both try to take the lock, Then only one holds it (edge).
  4. Given an audit entry, When written, Then it stores ids, hashes and the decision, and the schema has no column for a mail body (security; AC-22).
  5. Given a draft, When stored, Then it has an expiry, a hash and a used flag, and a used draft cannot be reused (security; AC-20).
  6. Given the application database user, When it connects, Then it has only the rights it needs (security).
