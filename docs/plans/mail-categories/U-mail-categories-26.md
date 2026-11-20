---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-26: Plan apply timing and the scheduling guard

- Component: mail-triage
- Layer: backend
- Release: R2
- Contract: the plan notice kinds in `telegram_action`; a delayed plan is claimed only after its notice was sent; cancel before the start follows the database clock; only `approve_plan` may schedule a plan or set `apply_after` (column grants plus a trigger guard, SQLSTATE 42501).
- Files: agents/mail-triage/migrations/versions/*, agents/mail-triage/app/db/grants.sql, agents/mail-triage/app/db/pg_plan.py, agents/mail-triage/tests/db/*
- Depends on: U-mail-categories-22, U-mail-categories-23
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a plan notice button kind, When it is stored, Then `telegram_action` allows it (type: happy)
  2. Given a delayed plan whose notice was not sent, When the apply poll runs, Then it is not claimed (type: edge)
  3. Given a cancel near the start time, When the clocks of the agent and the database differ, Then the database clock decides (type: edge)
  4. Given the agent role, When it tries to schedule a plan or lower `apply_after`, Then PostgreSQL refuses with SQLSTATE 42501 (type: security)
