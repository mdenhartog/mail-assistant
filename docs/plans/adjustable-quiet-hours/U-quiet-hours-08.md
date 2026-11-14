---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-08: PolicySource with fallback and notice

- Layer: integration (testcontainers PostgreSQL) with a fake slow port and `FakeClock`
- Contract: `PolicySource.current() -> TimePolicy`: reads with a 2 s timeout, validates, keeps a last-good policy in memory, returns `DEFAULT_POLICY` if none; logs `settings_invalid` or the error class without values; asks the notifier for one notice per incident.
- Files: `app/db/pg_policy_source.py`, `app/usecases/policy_notice.py`, `tests/db/test_policy_source.py`
- Depends on: U-quiet-hours-01, U-quiet-hours-05
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a stored valid row, When read, Then its policy; Given no row or no table, Then `DEFAULT_POLICY` (AC-1) (type: happy).
  2. Given an invalid row (unknown zone, 13 h window, overview inside the window, NULL), When read, Then last good or default, `settings_invalid` logged with the key only, and one notice (AC-31) (type: error).
  3. Given connection refused, timeout, permission error and a missing table (real database before migration), and a fake read slower than 2 s (injected clock, no `pg_sleep`), When read, Then the fallback within the timeout, the error class logged, one notice per incident (AC-32) (type: error).
  4. Given a good read, then a corrupted row, then a read, When run, Then the first values are used; Given a fresh process, Then the defaults (type: edge).
  5. Given any change or error, When logged, Then `Pacific/Kiritimati` never appears in any captured record and no token appears (AC-33) (type: security).
  6. Given an incident that continues over several reads, When it persists, Then only one notice is sent until it recovers (type: edge).
