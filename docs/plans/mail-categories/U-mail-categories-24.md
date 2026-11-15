---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-24: Plan progress, group approvals and the open-items badge

- Component: api
- Layer: backend
- Release: R2
- Contract: `GET /api/plan` exposes `estimate` and `notLookedAt` in `PlanProgress` (columns of migration 0016) and an `approved` count per `PlanGroup`; the review page shows "N of about M checked" and the not-looked-at number (AC-43) and an exact per-group summary (AC-13); `ProtectedShell` feeds the `openItems` badge of `MainNav` from `counts.pending` of `GET /api/plan`. The OpenAPI document and the web types are regenerated.
- Files: backend/app/plan_models.py, backend/app/plan_repo.py, backend/tests/test_plan_api.py, docs/api/openapi.json, docs/api/reference.md, apps/web/src/api/schema.d.ts, apps/web/src/features/review/*, apps/web/src/components/ProtectedShell.tsx, apps/web/e2e/*
- Depends on: U-mail-categories-17, U-mail-categories-18
- Parallel: yes
- Guardrails: guardrail-fastapi, guardrail-pydantic, guardrail-pytest, guardrail-react, guardrail-tanstack-query, guardrail-vitest-rtl, guardrail-a11y
- Criteria:
  1. Given a plan with estimate and not-looked-at values, When GET /api/plan is called, Then `progress` holds them and the contract test passes (AC-43) (type: happy)
  2. Given a plan being built, Then the page shows "N of about M checked" with a progress bar and the not-looked-at number once the plan is ready (AC-43) (type: happy)
  3. Given groups approved in different sessions, Then the summary dialog shows the exact approved count per group after a reload (AC-13) (type: edge)
  4. Given open items, Then the Review moves badge shows the pending count on every page and hides at zero (AC-23) (type: a11y)
  5. Given the canary strings, Then no sender or subject appears in any new field or log (MR-1) (type: security)
