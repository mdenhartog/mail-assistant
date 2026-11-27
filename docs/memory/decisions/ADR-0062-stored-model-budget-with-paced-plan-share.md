---
id: ADR-0062
title: "Stored daily model budget of 500 calls with a paced share for the plan"
status: accepted
area: architecture
tags: [daily-budget-partial-plan, mail-triage, budget, postgresql, security]
date: 2026-11-26
supersedes: ADR-0021 (budget counter only; the catch-up decisions stay)
guardrails: [guardrail-python, guardrail-sqlalchemy-alembic, guardrail-llm]
---

## Context

The budget is an in-memory counter on the agent's clock (ADR-0021). A restart gives a second budget, check and spend are two steps, and a plan that runs just after midnight can use almost all calls so that new mail (about 170 mails a day) keeps only the reserve of 50 (INT-011, threats T-01, T-02, T-05, T-06, T-15).

## Decision

1. `DAILY_MODEL_BUDGET` defaults to 500 (agent setting and compose). Settings validation bounds it to `reserve + 2 .. 1000`. The reserve of 50 stays in code.
2. The count is stored in a ledger table: one row per mailbox, UTC day (from the database clock) and purpose (`new_mail`, `plan`, `catch_up`). One definer function `spend(purpose, calls)` does a conditional atomic spend and returns whether it succeeded. The agent role has SELECT and EXECUTE only; the web role has nothing. A trigger refuses a decrease or a re-dated row. Rows older than 90 days are purged.
3. Every attempt that reaches the model provider counts as a call, including retries. An architecture test checks that every model call goes through the spend function.
4. **Pacing (option A, the user's choice):** until hour `h` of the UTC day the purpose `plan` may spend at most `(limit - reserve) * h / 24` calls of the day. `new_mail` may use the whole limit. The plan can therefore never leave new mail with less than the reserve plus its unspent share.

## Consequences

- One new table and one function in a migration; the agent needs no new library.
- At 500 calls the plan gets about 19 calls an hour (roughly 9 mails an hour), so a full day's plan work is about 225 mails.
- Provider cost rises by up to 2.5 times; a provider-side spending limit stays an operations control of the user.
- Accepted risk AR-A: a mail flood can use the whole budget so the plan does not progress; bounded by the budget and shown on the screen.
- Accepted risk AR-B: about 2.5 times more trimmed mail text goes to the same processor for the same purpose; recorded in the processing register.

## Alternatives

- A reserve sized from the new-mail volume of the last 7 days: better use of the budget but more complex and less predictable. Rejected (the user chose the fixed pace).
- Keep the in-memory counter and only raise the number: a restart could double the spend. Rejected.
- A budget in Redis: a new component for one counter. Rejected.
