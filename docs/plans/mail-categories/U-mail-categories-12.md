---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-12: Plan schema and decision functions

- Component: mail-triage
- Layer: backend
- Release: R2
- Contract: Alembic revision: `plan` (partial unique index: one non-terminal plan per mailbox), `plan_item`, `plan_decision`, `plan_approval`, `apply_audit`, `move_back_request`; functions `record_decision` and `approve_plan` (SECURITY DEFINER, fixed `search_path`, revoked from PUBLIC, EXECUTE for the api only); grants of the matrix; retention in `purge_expired()`.
- Files: agents/mail-triage/migrations/versions/*, agents/mail-triage/app/db/grants.sql, agents/mail-triage/tests/db/test_plan_*.py
- Depends on: U-mail-categories-03
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the api role, When it inserts, updates or deletes plan items or writes decision, approval or audit tables directly, Then SQLSTATE 42501 (AC-27) (type: security)
  2. Given a plan `ready`, When `record_decision` is called with the right count, Then decisions are set and `plan_decision` has an append-only row (AC-13, AC-36) (type: happy)
  3. Given a wrong count, an id of another plan or mailbox, more than 200 ids, or a plan not `ready`, Then a 409 error and nothing changes (AC-27, AC-32) (type: error)
  4. Given `approve_plan` below and above the threshold read from `apply_config`, Then `scheduled` with `apply_after` now or now + delay; 49 + 49 approvals within 24 hours wait at the second (AC-42) (type: security)
  5. Given pending items at approval, Then they become `rejected` and enter `rejection` (AC-13, AC-47) (type: happy)
  6. Given two connections, When Cancel and the start of the apply race, Then exactly one wins (compare-and-set) (type: edge)
  7. Given a repeated `approve_plan` on a `scheduled` plan, Then it returns the current state (type: edge)
  8. Given retention with owner fixtures, Then items go 14 days after the last decision or at apply, audit after a year, `rejection` stays until the list changes (AC-19, AC-47) (type: happy)
  9. Given the functions, Then owner, search_path, PUBLIC and EXECUTE are as designed and no dynamic SQL is built (AC-56) (type: security)
