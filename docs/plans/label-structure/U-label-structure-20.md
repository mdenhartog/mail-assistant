---
intent: INT-008
feature: label-structure
---

# U-label-structure-20: The sort-again request, plan columns and the approval functions (R2)

- Component: mail-triage
- Layer: backend
- Contract: an Alembic revision (ADR-0056): insert-only `resort_request` (threshold 50 to 100, actor digest and channel derived); `plan.kind`, `plan.request_id`, `plan.threshold`; the partial unique index per `(mailbox_id, kind)`; `plan_item` pair columns, `confidence_pct`, `decision_source`, `tip`; `SECURITY DEFINER` functions `request_resort(mailbox_id, threshold)` (api role) and `approve_system_plan(plan_id)` (agent role, re-checks every item against the stored threshold, records the decision source `threshold`, inserts the approval that counts toward the rolling 24 hours and sets `scheduled`); grants; the downgrade.
- Files: `agents/mail-triage/migrations/versions/<new revision>.py`, `agents/mail-triage/app/db/grants.sql`, tests in `agents/mail-triage/tests/db/`
- Depends on: U-label-structure-05, U-label-structure-17
- Parallel: yes
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a threshold from 50 to 100, When `request_resort` is called by the api role, Then one request row exists; 49, 101, a fraction or null is refused. (type: happy)
  2. Given a plan already open for the mailbox and kind, When `request_resort` is called, Then it is refused. (type: error)
  3. Given the api role, When it calls `approve_system_plan` or writes an approval, a decision or a plan item directly, Then PostgreSQL refuses (SQLSTATE 42501). (type: security)
  4. Given the agent role and an `auto` plan whose items have confidence below the stored threshold, When it calls `approve_system_plan`, Then the function refuses; with qualifying items it approves, records the decision source `threshold` and counts the approval toward the 24-hour wait. (type: security)
  5. Given a later request with another threshold, When a running plan exists, Then the plan keeps its copied threshold. (type: edge)
  6. Given the migration, When it runs twice and its downgrade runs, Then it is idempotent and reversible. (type: edge)
