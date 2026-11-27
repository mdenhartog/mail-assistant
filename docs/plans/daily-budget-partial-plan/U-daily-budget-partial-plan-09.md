---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-09: Build in parts

- Component: mail-triage agent
- Layer: backend
- Contract: `usecases/resort_build.py` is rebuilt (no flag) so that a build that the budget or the pace stops closes the checked mails as a part (U-08), and the next part starts after the cursor of the previous one on a later UTC day (U-06 decides). The estimate and the 5 000-mail cap count the whole series. The pause reason is stored as one of the fixed values. A build with nothing checked keeps waiting. No mail of an earlier part is judged again.
- Files: `agents/mail-triage/app/usecases/resort_build.py`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/app/wiring.py`, tests under `agents/mail-triage/tests/usecases/`
- Depends on: U-daily-budget-partial-plan-01, U-daily-budget-partial-plan-05, U-daily-budget-partial-plan-06, U-daily-budget-partial-plan-07, U-daily-budget-partial-plan-08
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-llm
- Criteria:
  1. Given a build with 60 calls left above the reserve, When the next mail needs 2 calls and fewer are left, Then the build stops with the reason `budget` and the checked mails close as part 1 (AC 2). (type: happy)
  2. Given part 1 is finished, When the next budget day starts, Then part 2 starts after the cursor and no mail of part 1 is judged again (AC 4). (type: happy)
  3. Given part 1 is still open, When the next day starts, Then part 2 does not start and the pause reason is `waiting_for_part` (AC 5). (type: edge)
  4. Given 5 000 mails over several parts, When the cap is reached, Then no further part starts and the rest is "not looked at" (AC 7). (type: edge)
  5. Given the cursor mail was deleted, When part 2 starts, Then it continues after that mail's date (AC 19). (type: edge)
  6. Given the build stops at the paced share, When the day goes on, Then the build goes on in the same part until the hour allows more or the budget is spent (AC 22). (type: happy)
  7. Given new mail arrives while a plan builds and the budget is low, When both run, Then new mail still gets its calls (AC 9). (type: happy)
  8. Given logs and audit, When a part closes or waits, Then they hold numbers only (AC 14). (type: security)
