---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-13: Overview window across zone changes

- Layer: backend
- Contract: the daily overview takes its window from the last settled instant, uses the policy zone for the "already sent for this date" check, and has no `TIME_ZONE`/`OVERVIEW_AT` constants; the dead "yesterday" branch is removed.
- Files: `app/usecases/overview.py`, `tests/usecases/test_overview.py`
- Depends on: U-quiet-hours-03, U-quiet-hours-08
- Parallel: yes (with U-12)
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the overview sent today in Europe/Amsterdam, When the zone becomes America/New_York the same evening, Then no second overview for that local date, no filed mail is dropped, and the next is at 18:00 New York time (AC-27) (type: edge).
  2. Given the existing overview tests with `DEFAULT_POLICY`, When run, Then they pass unchanged (AC-1) (type: happy).
  3. Given a zone change from New York back to Amsterdam, When the day is repeated or skipped locally, Then every filed mail appears in exactly one overview (AC-27) (type: edge).
  4. Given a changed overview time, When the policy is read, Then the new time is used for the next overview only (type: happy).
