---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-02: Migration (expand): the model-budget ledger and its spend function

- Component: mail-triage agent
- Layer: backend
- Contract: One new Alembic revision (the next free number after 0030; 0031 stays reserved for the INT-010 contract migration) with `categories.model_budget_ledger` (mailbox, UTC day from the database clock, purpose `new_mail | plan | catch_up`, calls), the definer function `categories.spend_model_calls(mailbox, purpose, calls, limit, floor)` that does one conditional atomic spend and returns whether it succeeded, a trigger that refuses a decrease or a re-dated row, a purge of rows older than 90 days, and grants: agent role SELECT and EXECUTE only, web role nothing. The downgrade drops them. The day and the hour always come from one function `categories.utc_now()` (default `now()`); test fixtures override it as superuser, so tests can move the clock and the agent's own clock is never used (SAC-1). Two-session tests use two real connections and a barrier (testcontainers).
- Files: `agents/mail-triage/app/db/versions/00NN_model_budget_ledger.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/app/db/grants.sql`, `agents/mail-triage/app/db/purge.py`, tests under `agents/mail-triage/tests/db/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given 120 calls spent today, When a new session reads the ledger, Then 120 still count and the day is the database's UTC date (SAC-1, AC 8). (type: security)
  2. Given 3 calls left above the floor, When two sessions each spend 2 at once, Then exactly one succeeds and the ledger never exceeds the limit (SAC-2, AC 21). (type: security)
  3. Given the web role, When it reads, writes or calls the function, Then every attempt fails with 42501 (SAC-8). (type: security)
  4. Given the agent role, When it updates or deletes a ledger row or lowers a count, Then it fails (SAC-8). (type: security)
  5. Given the day changes at midnight UTC, When a spend is made, Then the count for the new day starts at zero once (AC 13). (type: edge)
  6. Given a row older than 90 days, When the purge runs, Then it is removed and today's row stays. (type: edge)
  7. Given the migration, When it is upgraded and downgraded, Then both complete and the schema matches the models. (type: happy)
  8. Given `utc_now()` is set to 23:59:59 and then to 00:00:01 of the next day, When a spend is made each time, Then the two spends land on two different day rows. (type: edge)
