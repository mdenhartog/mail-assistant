---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-25: Connect the daily re-file report to PostgreSQL and Gmail

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: the PostgreSQL store of U-10 (`RefileStore`: newest `filing` row per mail in the last 14 days, category id to label id from `category_label` including Other, `record_report`), a table for the report counts (migration, grants for the runtime role, retention in `purge_expired()`), the Gmail mailbox (`label_names`, `fetch` returning none for a deleted mail) with a cap on mails checked per run, the daily gating (once per day, injected clock) and the runner call, with the cap and the hour from settings.
- Files: agents/mail-triage/app/db/pg_refile.py, agents/mail-triage/migrations/versions/*, agents/mail-triage/app/db/grants.sql, agents/mail-triage/app/runner.py, agents/mail-triage/app/wiring.py, agents/mail-triage/app/settings.py, agents/mail-triage/compose.yaml, agents/mail-triage/tests/db/test_pg_refile.py, agents/mail-triage/tests/test_runner_refile.py
- Depends on: U-mail-categories-10, U-mail-categories-23
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-sqlalchemy-alembic, guardrail-gmail
- Criteria:
  1. Given filings in the last 14 days on the real database as the agent role, When the report runs, Then it reports the re-filed share and the share under Other (AC-46) (type: happy)
  2. Given the runner, When two cycles run in one day, Then the report runs once (type: edge)
  3. Given more filings than the cap, When the report runs, Then at most the cap is fetched from Gmail and the report says how many were checked (type: edge)
  4. Given the grants matrix, Then the runtime role can neither read nor write the report table and rows past their retention are purged by `purge_expired()` (type: security)
  5. Given the canary strings, Then no sender or subject is in the report row, the log or any message (AC-30) (type: security)
