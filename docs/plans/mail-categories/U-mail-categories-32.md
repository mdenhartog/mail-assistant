---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-32: Plan view: example, apply settings, moved count

- Component: api
- Layer: backend
- Release: R2
- Contract: `GET /api/plan` shows per group an example mail (sender name, address, subject), the apply threshold and delay, and the moved count; `plan.moved_count` is kept by `remove_applied_items`; the api may read `categories.apply_config`; the review page shows the example, the stored decisions, the threshold and delay in the approve summary and the moved count in the applied banner.
- Files: backend/app/**, agents/mail-triage/migrations/versions/*, agents/mail-triage/app/db/grants.sql, apps/web/src/features/review/**
- Depends on: U-mail-categories-17, U-mail-categories-24
- Parallel: no
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-react, guardrail-typescript
- Criteria:
  1. Given an applied plan, Then the plan keeps how many mails were moved (type: happy)
  2. Given a plan group, Then the view shows an example mail (type: happy)
  3. Given the apply settings, Then the view shows the threshold and the delay, or null without a delay (type: edge)
  4. Given the api role, Then it may read `categories.apply_config` and no other new table (type: security)
  5. Given the example mail, Then it is shown as text only and passes the canary check (type: security)
