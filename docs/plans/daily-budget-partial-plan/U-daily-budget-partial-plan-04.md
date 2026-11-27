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
  1. Given a full budget at 00:30 UTC, When the allowance is asked, Then it is at most 9 calls (SAC-7, AC 22). (type: happy)
  2. Given 12:00 UTC and nothing spent, When asked, Then the allowance is 225 (half of 450). (type: happy)
  3. Given the plan has already spent its share, When asked, Then the allowance is 0 and never negative. (type: edge)
  4. Given hour 24 or more (end of day), When asked, Then the allowance is the whole of `limit - reserve` minus what was spent. (type: edge)
  5. Given any input (property test), When asked, Then `spent + allowance` never exceeds `limit - reserve` (AC 9). (type: security)
