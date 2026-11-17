---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-28: Review fixes: hidden SQL parameters, debounce, retries, notice wording

- Component: mail-triage
- Layer: backend
- Release: R2
- Contract: database errors hide statement parameters; the build debounce comes from the settings only; failed move attempts spread across apply runs; the delayed notice states the zone and names its buttons; the list notice shows every changed category first; a retried apply re-checks scope, archive and pinning.
- Files: backend/app/database.py, agents/mail-triage/app/**, backend/tests/test_database_hide_parameters.py, agents/mail-triage/tests/**
- Depends on: U-mail-categories-22
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a failing statement, When the error is raised, Then no parameter value is in it (type: security)
  2. Given the settings, When the plan debounce is read, Then only the settings value is used (type: edge)
  3. Given a failed move, When apply runs repeat, Then the attempts are spread across runs (type: edge)
  4. Given a delayed plan, When its notice is written, Then it states the zone and names the buttons (type: happy)
  5. Given a retried apply, When it runs, Then scope, archive and pinning are checked again (type: security)
