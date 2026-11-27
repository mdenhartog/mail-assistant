---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-04: The pacing rule (pure)

- Component: mail-triage agent
- Layer: backend
- Contract: A pure `core/budget_pace.py`: `plan_allowance(limit, reserve, hour_utc, spent_by_plan) -> int` returns how many calls the plan may still spend now, from `(limit - reserve) * h / 24` (ADR-0062 decision 4, the user's choice A). No clock, no I/O. `new_mail` may use the whole limit and is not paced.
- Files: `agents/mail-triage/app/core/budget_pace.py`, tests under `agents/mail-triage/tests/core/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given limit 500, reserve 50, hour 0 (integer hours, floor) and nothing spent, When asked, Then the allowance is 0; given hour 1, Then 18 (SAC-7, AC 22). (type: happy)
  2. Given hour 12 and nothing spent, When asked, Then the allowance is 225 (half of 450). (type: happy)
  3. Given the plan has already spent its share, When asked, Then the allowance is 0 and never negative. (type: edge)
  4. Given hour 23 and nothing spent, When asked, Then the allowance is 431; the hour is always 0 to 23. (type: edge)
  5. Given any input (property test), When asked, Then `spent + allowance` never exceeds `limit - reserve` (AC 9). (type: security)

Mutation testing runs on this unit (the arithmetic is the risk); coverage of the changed code is at least 90 %.
