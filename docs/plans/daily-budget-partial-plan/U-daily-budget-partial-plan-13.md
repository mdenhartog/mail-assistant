---
intent: INT-011
feature: daily-budget-partial-plan
---

# U-daily-budget-partial-plan-13: End-to-end: the journey of a paused part

- Component: web
- Layer: web
- Contract: A Playwright project `daily-budget-partial-plan` with stubs for the plan view: a paused plan (budget), a ready part 1 with the rest waiting, a part 2 that waits for part 1, an expired series and the 409 on Sort again, at 375, 768 and 1280 px, light and dark, with axe and a horizontal-scroll check. Stubs carry every field the real api returns.
- Files: `apps/web/e2e/daily-budget-partial-plan.spec.ts`, `apps/web/e2e/support/stubs.ts`, `apps/web/e2e/support/states.ts`, `apps/web/playwright.config.ts`
- Depends on: U-daily-budget-partial-plan-12
- Parallel: no
- Guardrails: guardrail-playwright, guardrail-a11y, guardrail-typescript
- Criteria:
  1. Given the paused plan, When the user opens "Review moves", Then the budget sentence and the checked count show at every viewport (AC 11). (type: happy)
  2. Given a ready part 1 with more mail waiting, When it opens, Then the part number shows and the rest is said to continue (AC 12). (type: happy)
  3. Given part 2 waits for part 1, When it opens, Then the waiting sentence shows (AC 5). (type: edge)
  4. Given an expired series, When it opens, Then the plain sentence shows and no part is offered (AC 16). (type: edge)
  5. Given the 409, When the user sorts again, Then the plain message shows (AC 17). (type: error)
  6. Given every state, When axe runs, Then there is no violation in both schemes and no horizontal scroll (AC 11). (type: a11y)
