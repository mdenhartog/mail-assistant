---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-13: Plan state machine

- Component: mail-triage
- Layer: backend
- Release: R2
- Contract: `core/resort_plan.py` (pure): plan transitions `building, ready, scheduled, applying, applied, replaced, discarded, cancelled` and item transitions with the rules of the design (list change, Lock, Cancel, finish-first).
- Files: agents/mail-triage/app/core/resort_plan.py, agents/mail-triage/tests/core/test_resort_plan.py
- Depends on: U-mail-categories-02
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given each allowed transition, Then it succeeds; every other transition is refused (table-driven) (type: happy)
  2. Given a list change in `building` or `ready`, Then the plan becomes `replaced` and decisions are discarded (AC-16) (type: edge)
  3. Given a list change in `scheduled` or `applying`, Then the plan finishes first and the next build waits (AC-50) (type: edge)
  4. Given Lock or Cancel in `scheduled`, Then `cancelled`; in `applying`, Then it stops before the next batch (AC-42, AC-57) (type: security)
  5. Given a `ready` plan older than 14 days, Then `discarded` (AC-19) (type: edge)
  6. Given a fake clock, Then `apply_after` decides when `scheduled` may start (type: happy)
