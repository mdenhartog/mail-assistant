---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-33: Last plan

- Component: api
- Layer: backend
- Release: R2
- Contract: the last plan is the plan that ended most recently as applied, cancelled or replaced, with its end time; the review page shows it.
- Files: backend/app/plan_models.py, backend/app/**, apps/web/src/features/review/**
- Depends on: U-mail-categories-32
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-react
- Criteria:
  1. Given applied, cancelled and replaced plans, Then the last plan is the one that ended most recently (type: happy)
  2. Given a last plan, Then it carries its end time (type: happy)
  3. Given no ended plan, Then there is no last plan (type: edge)
