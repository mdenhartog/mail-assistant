---
intent: INT-002
feature: web-settings
---

# U-web-settings-56: Undo burst is identified by an explicit id (R1; challenge fix; CR-07)

- Layer: agent, database (migration 0009)
- Contract: each Undo token record stores `burst_id` and `first_version`; the guard uses them instead of comparing `before` values; a partial send failure keeps the original burst.
- Files: `agents/mail-triage/migrations/versions/0009_notice_burst.py`, `agents/mail-triage/app/usecases/web_notice.py`, `agents/mail-triage/app/usecases/web_notice_actions.py`, `agents/mail-triage/tests/db/test_web_notice.py`
- Depends on: U-web-settings-27
- Parallel: yes
- Guardrails: guardrail-telegram, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given two bursts whose `before` values are equal inside 24 hours, When Undo is pressed on the older notice, Then only that burst is restored or refused as changed (AC-13) (type: edge; level: db).
  2. Given a send failure after the first notice of a burst, When retried and Undo is pressed on the first notice, Then the pre-burst values return (type: error; level: db).
  3. Given migration 0009, When run up, down and up, Then it is reversible (type: edge; level: db).
