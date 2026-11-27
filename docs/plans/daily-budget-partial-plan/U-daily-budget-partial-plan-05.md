---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-05: The stored budget replaces the in-memory counter

- Component: mail-triage agent
- Layer: backend
- Contract: `db/pg_budget.py` implements `BudgetView` and the spend of `AnthropicJudge` on the ledger function of U-02, for the purposes `new_mail`, `plan` and `catch_up`. `remaining(purpose)` reads the ledger; `try_spend(purpose)` calls the function with the reserve as floor for `plan` and `catch_up`, and the pace rule of U-04 for `plan`. Every attempt that reaches the model provider (including `ModelPoster` retries) counts as a call. `DailyBudget` is removed (rebuild, no flag). An architecture test asserts that every model call goes through the spend path.
- Files: `agents/mail-triage/app/db/pg_budget.py`, `agents/mail-triage/app/adapters/judge_anthropic.py`, `agents/mail-triage/app/wiring.py`, `agents/mail-triage/app/usecases/catchup.py`, tests under `agents/mail-triage/tests/`
- Depends on: U-daily-budget-partial-plan-02, U-daily-budget-partial-plan-04
- Parallel: no
- Guardrails: guardrail-python, guardrail-sqlalchemy-alembic, guardrail-llm, guardrail-pytest
- Criteria:
  1. Given 120 calls spent today, When the agent restarts, Then 120 still count (SAC-1, AC 8). (type: security)
  2. Given the model answers 429 twice and then 200, When one judgement is made, Then the ledger counts three attempts (SAC-5). (type: security)
  3. Given a mail whose text tells the model to be unsure, When it is judged, Then at most `CALLS_PER_MAIL` calls are made (SAC-6). (type: security)
  4. Given new mail and a low budget, When the plan and new mail both spend, Then new mail still gets its 50 calls and the plan stops first (AC 9). (type: happy)
  5. Given the build runs at 00:30 UTC with a full budget, When it spends, Then it stops at the paced share (SAC-7, AC 22). (type: happy)
  6. Given the code base, When the architecture test runs, Then every model call path goes through the spend function (SAC-18). (type: security)
  7. Given logs and audit, When a spend is refused, Then they hold integers and fixed values only (AC 14, SAC-17). (type: security)
  8. Given the agent's own clock is 10 minutes ahead at 23:55 database time, When it spends, Then the day and the pace hour are the database's (SAC-1). (type: security)
  9. Given the budget is gone after the first HTTP attempt of a judgement, When the retry would follow, Then no further HTTP call is made. (type: edge)

The day and the hour come from `categories.utc_now()` (U-02); the pure rules receive them as arguments.
