---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-22: Connect plan build and apply to PostgreSQL and Gmail

- Component: mail-triage
- Layer: backend
- Release: R2
- Contract: the PostgreSQL implementations of the build store (`BuildStore` of U-14: compare-and-set progress, replace plan, complete build) and the apply and move-back stores of U-15, the Gmail implementation of the build mailbox (`BuildMailbox`: label names, in-scope estimate, candidates with a resume cursor, fetch returning none for a deleted mail), and the scheduling that calls the build, apply and move-back each cycle in the runner, with settings (debounce, cap, apply poll) from configuration. Nothing here changes a state machine or a port.
- Files: agents/mail-triage/app/db/pg_resort.py, agents/mail-triage/app/adapters/gmail_build.py, agents/mail-triage/app/runner.py, agents/mail-triage/app/wiring.py, agents/mail-triage/app/settings.py, agents/mail-triage/compose.yaml, agents/mail-triage/tests/db/test_pg_resort.py, agents/mail-triage/tests/test_gmail_build.py, agents/mail-triage/tests/test_runner_resort.py
- Depends on: U-mail-categories-14, U-mail-categories-15, U-mail-categories-21
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-sqlalchemy-alembic, guardrail-gmail
- Criteria:
  1. Given the real database as the agent role, When the build writes progress, replaces a plan or completes, Then the compare-and-set rules of the ports hold and a replaced plan gets no more items (type: happy)
  2. Given two agent processes, When both try to complete or apply the same plan, Then exactly one wins (type: edge)
  3. Given the Gmail fake, When candidates are listed, Then deleted mail returns none from fetch, the cursor resumes after a crash and mail outside the scope is not offered (type: edge)
  4. Given the runner, When a cycle runs, Then build, apply and move-back are called in that order and a failure in one is logged without content and does not stop the others (type: error)
  5. Given the configuration, Then the debounce, the cap and the apply poll come from settings, not from constants (type: happy)
