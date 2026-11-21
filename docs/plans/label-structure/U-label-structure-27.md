---
intent: INT-008
feature: label-structure
---

# U-label-structure-27: End-to-end journey for R2

- Component: web
- Layer: web
- Contract: Playwright journeys against the prod-like stack in CI (never the user's local compose project): type a threshold, press "Sort everything again", see the notice numbers, the sure items moved after the delay, the rest in Review moves with its tip; archive label change; three viewports with axe.
- Files: `apps/web/e2e/label-structure-r2.spec.ts`, `apps/web/e2e/support/`
- Depends on: U-label-structure-25, U-label-structure-26
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y, guardrail-typescript
- Criteria:
  1. Given a seeded mailbox and a threshold, When the user presses the button, Then the plan is made, the numbers are shown and nothing moves before the delay. (type: happy)
  2. Given the delay has passed, When the apply runs, Then the sure items moved and the rest are in Review moves with their tips. (type: happy)
  3. Given a Cancel before the delay, When pressed, Then nothing moved. (type: edge)
  4. Given the archive label field, When changed, Then the label is renamed and archived mail stays out of the plan. (type: edge)
  5. Given the pages, When axe runs in three viewports, Then it finds no violations. (type: a11y)
