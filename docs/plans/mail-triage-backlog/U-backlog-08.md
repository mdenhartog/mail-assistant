---
intent: INT-003
feature: mail-triage-backlog
---

# U-backlog-08: CatchUp use case: budget and reserve

- Layer: backend (use case)
- Contract: before each mail `CatchUp` stops for the day when `budget.remaining() < BUDGET_RESERVE + 2` (`BUDGET_RESERVE = 50`; two calls cover the small and the large model). As a second guard it also stops, without filing, if the verdict is `NeedsAttention("budget")`. A stopped run leaves the mail untouched in the inbox and does not finish the catch-up.
- Files: `app/usecases/catchup.py`, `tests/usecases/test_catchup.py`
- Depends on: U-07
- Parallel: no
- Guardrails: guardrail-llm
- Criteria:
  1. Given a remaining budget of 51 or less, When it runs, Then no mail is judged and none is touched (type: happy; AC-B8, AC-B15).
  2. Given a remaining budget of 52 and three mails, When it runs, Then the first mail is judged and the run stops once fewer than 52 remain (type: edge; AC-B15).
  3. Given the budget is used up, When it runs, Then no mail is labelled `Assistant/Other` and no alert is created (type: security; AC-B8, T-23).
  4. Given the next day (budget restored), When it runs, Then it continues with the remaining mails (type: happy; AC-B8).
  5. Given the judge still returns `NeedsAttention("budget")`, When it runs, Then the mail is not filed and the run stops (type: error; AC-B8).
  6. Given new mail and old mail in the same cycle, When the pipeline runs first and uses the budget, Then the catch-up only gets what is above the reserve (type: edge; AC-B7, AC-B15).
