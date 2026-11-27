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
  1. Given 1 call left above the reserve and a mail that needs 2, When the build reaches it, Then the build stops with the reason `budget` and the mails checked before it close as part 1 (AC 2). (type: happy)
  2. Given part 1 is finished, When the next budget day starts, Then part 2 starts after the cursor and no mail of part 1 is judged again (AC 4). (type: happy)
  3. Given part 1 is still open, When the next day starts, Then part 2 does not start and the pause reason is `waiting_for_part` (AC 5). (type: edge)
  4. Given 5 000 mails over several parts, When the cap is reached, Then no further part starts and the rest is "not looked at" (AC 7). (type: edge)
  5. Given the cursor mail was deleted, When part 2 starts, Then it continues after that mail's date (AC 19). (type: edge)
  6. Given the build stops at the paced share, When the day goes on, Then the build goes on in the same part until the hour allows more or the budget is spent (AC 22). (type: happy)
  7. Given logs and audit, When a part closes or waits, Then they hold numbers only (AC 14). (type: security)
  8. Given the build is stopped by the pace, When the pause is stored, Then the reason is `pace`; given it is stopped by the budget, Then `budget`; given the cursor mark is lost, Then `cursor_lost` (AC 11, D13). (type: edge)
  9. Given a part open for 14 days, When the next budget day starts, Then the series ends with `expired` and the build starts no part (AC 16, SAC-12). (type: security)
  10. Given a build at 23:59 UTC when midnight passes, When it goes on, Then the day and the pace hour reset once, the part stays one part and part 2 starts only on a later run (D10). (type: edge)

The cap is injectable in tests (the default stays 5 000).
